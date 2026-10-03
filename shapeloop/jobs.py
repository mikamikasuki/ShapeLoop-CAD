from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .store import Store, now

class JobManager:
    def __init__(self, store: Store, settings, accepted_callback=None):
        self.store, self.settings = store, settings
        self.accepted_callback = accepted_callback
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=settings.value["workers"]["max_workers"], thread_name_prefix="shapeloop")
        self.cancellations: dict[str, threading.Event] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        store.recover_jobs()

    def submit(self, revision_id: str, auto_accept=False) -> dict:
        with self.lock:
            active = [j for j in self.store.list("job") if j["status"] in {"queued", "running", "verifying"}]
            if len(active) >= self.settings.value["workers"]["max_queue"]:
                raise ValueError("Geometry job queue is full")
            if any(j["revision_id"] == revision_id for j in active):
                raise ValueError("This revision already has an active build")
            revision = self.store.get(revision_id, "revision")
            job = self.store.insert("job", {"revision_id":revision_id, "status":"queued", "phase":"queued", "error":None, "owner_pid":os.getpid()}, revision["project_id"])
            self.cancellations[job["id"]] = threading.Event()
            self.store.update(revision_id, status="building", job_id=job["id"])
            self.store.event(job["id"], {"status":"queued", "revision_id":revision_id})
            self.pool.submit(self._run, job, revision, auto_accept)
            return job

    def _phase(self, job, status):
        self.store.update(job["id"], status=status, phase=status)
        self.store.event(job["id"], {"status":status})

    def _process(self, mode: str, job: dict, request_path: Path, work: Path) -> dict:
        result_path = work / f"{mode}-result.json"
        logfile = work / f"{mode}.log"
        limits = self.settings.value["workers"]
        # Worker environment excludes provider credentials and unrelated app secrets.
        environment = {k:v for k,v in os.environ.items() if k in {"PATH","TMPDIR","SYSTEMROOT","LD_LIBRARY_PATH","DYLD_LIBRARY_PATH"}}
        environment["PYTHONPATH"] = str(Path(__file__).parent.parent)
        with logfile.open("wb") as output:
            proc = subprocess.Popen([sys.executable,"-m","shapeloop.worker",mode,str(request_path),str(result_path)], stdout=output, stderr=output, cwd=work, env=environment)
            with self.lock:
                self.processes[job["id"]] = proc
            started = time.monotonic()
            failure = None
            while proc.poll() is None:
                if self.cancellations[job["id"]].is_set():
                    failure = "cancelled"
                elif time.monotonic()-started > limits["timeout_seconds"]:
                    failure = f"Worker timeout after {limits['timeout_seconds']} seconds"
                elif logfile.stat().st_size > limits["output_mb"]*1024**2:
                    failure = "Worker output limit exceeded"
                # Host RSS cap supplements native resource limits.
                if not failure and sys.platform != "win32":
                    try:
                        rss = subprocess.run(["ps","-o","rss=","-p",str(proc.pid)], capture_output=True, text=True, timeout=1).stdout.strip()
                        if rss and int(rss) > limits["memory_mb"]*1024:
                            failure = "Worker memory limit exceeded"
                    except (ValueError, subprocess.SubprocessError):
                        pass
                if failure:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait()
                    break
                time.sleep(0.15)
        with self.lock:
            self.processes.pop(job["id"], None)
        if failure:
            raise RuntimeError(failure)
        if not result_path.exists():
            raise RuntimeError(f"{mode} worker exited {proc.returncode} without a result")
        result = json.loads(result_path.read_text())
        if not result["ok"]:
            raise RuntimeError(f"{mode}: {result['error']}")
        return result["result"]

    def _run(self, job, revision, auto_accept):
        work = self.store.root / "jobs" / job["id"]
        artifacts = work / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        try:
            if self.cancellations[job["id"]].is_set():
                raise RuntimeError("cancelled")
            started = time.monotonic()
            self._phase(job, "running")
            request_path = work / "request.json"
            request_path.write_text(json.dumps({"spec":revision["spec"],"output_dir":str(artifacts),"limits":self.settings.value["workers"],"cache_dir":str(self.store.root/'geometry-cache')}))
            built = self._process("build",job,request_path,work)
            from .compiler import compile_source
            from copy import deepcopy
            export_spec=deepcopy(revision['spec'])
            for feature in export_spec['features']:
                if feature['type']=='import_step':
                    filename=f"reference_{feature['id']}.step"
                    shutil.copy2(feature['parameters']['path'],artifacts/filename)
                    feature['parameters']['path']=filename
            (artifacts / "design.py").write_text(compile_source(export_spec))
            (artifacts / "parameters.json").write_text(json.dumps({k:p['value'] for k,p in revision['spec']['parameters'].items()},indent=2))
            (artifacts / "REBUILD.txt").write_text("Python 3.12, cadquery==2.5.2 and pydantic==2.11.4.\nRebuild independently: python design.py --output rebuilt\nOverride named parameters: python design.py --parameters parameters.json --output rebuilt\nCoordinates are millimeters; STL files have no intrinsic unit declaration.\nSTEP does not contain original feature history. Source and design.json preserve editable intent.\n")
            self._phase(job,"verifying")
            report = self._process("verify",job,request_path,work)
            from .verifier import analytic_conflicts
            report['conflicts']=analytic_conflicts(revision['spec'])
            (artifacts / "report.json").write_text(json.dumps(report, indent=2))
            (artifacts / "design.json").write_text(json.dumps(export_spec, indent=2))
            manifest = {"revision_id":revision["id"], "spec_sha256":hashlib.sha256(json.dumps(revision["spec"],sort_keys=True).encode()).hexdigest(), "units":"mm", "files":{}}
            for file in artifacts.iterdir():
                if file.is_file():
                    manifest["files"][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
            (artifacts / "manifest.json").write_text(json.dumps(manifest,indent=2))
            with zipfile.ZipFile(artifacts / "bundle.zip","w",zipfile.ZIP_DEFLATED) as bundle:
                for file in artifacts.iterdir():
                    if file.name != "bundle.zip" and file.is_file():
                        bundle.write(file, file.name)
            target = self.store.root / "artifacts" / revision["id"]
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(artifacts),target)
            status = "candidate" if report.get("status") == "PASS" else "failed"
            files = [p.name for p in target.iterdir() if p.is_file()]
            artifact_hashes={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in files}
            self.store.update(revision["id"], status=status, report=report, artifacts=files, artifact_hashes=artifact_hashes, geometry=built, error=None if status=="candidate" else "Required geometry checks did not pass")
            self.store.update(job["id"], status="succeeded" if status=="candidate" else "failed", phase="complete", result={"report":report,"artifacts":files}, duration_seconds=time.monotonic()-started, error=None if status=="candidate" else "Required geometry checks did not pass")
            self.store.event(job["id"], {"status":"succeeded" if status=="candidate" else "failed", "report":report})
            if status=="candidate" and auto_accept and self.accepted_callback:
                self.accepted_callback(revision["id"])
        except BaseException as error:
            cancelled = str(error)=="cancelled"
            status = "cancelled" if cancelled else "failed"
            self.store.update(job["id"],status=status,error=str(error),phase="complete")
            self.store.update(revision["id"],status=status,error=str(error))
            self.store.event(job["id"],{"status":status,"error":str(error)})

    def cancel(self, id: str):
        job = self.store.get(id,"job")
        if job["status"] not in {"queued","running","verifying"}:
            return job
        if id not in self.cancellations:
            raise ValueError('This job belongs to another running local service; cancel it through that service')
        self.cancellations[id].set()
        return self.store.update(id,status="cancelling")

    def wait(self,id: str,timeout=600):
        start = time.monotonic()
        while time.monotonic()-start < timeout:
            job = self.store.get(id,"job")
            if job["status"] not in {"queued","running","verifying","cancelling"}:
                return job
            time.sleep(0.2)
        raise TimeoutError("Timed out waiting for geometry job")

    def close(self):
        for event in self.cancellations.values():
            event.set()
        self.pool.shutdown(wait=True, cancel_futures=True)

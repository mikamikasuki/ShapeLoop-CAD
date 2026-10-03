"""Shared domain services used by the API and CLI."""
from __future__ import annotations
import hashlib
import json
import shutil
import threading
from copy import deepcopy
from pathlib import Path
from .config import Settings
from .jobs import JobManager
from .spec import DesignSpec, UNITS, normalize, NUMBER_KEYS, ANGLE_KEYS, TEXT_KEYS
from .recipes import recipe
from .store import Store, data_directory

class StaleRevision(ValueError):
    pass

class Service:
    def __init__(self, root: Path | None = None):
        self.store = Store(root or data_directory())
        self.settings = Settings(self.store.root)
        self.lock = threading.RLock()
        self.jobs = JobManager(self.store, self.settings, self.accept)
        self._scout = None

    def close(self):
        if self._scout is not None:
            self._scout.stop_watch()
        self.jobs.close()

    def projects(self):
        return self.store.list("project")

    def project(self, id: str):
        project = self.store.get(id,"project")
        project["revisions"] = self.store.list("revision", id)
        project["active_revision"] = project.get("active_revision_id")
        return project

    def _revision(self, project_id, spec, parent_id=None, branch="main", proposal=None):
        validated = DesignSpec.model_validate(spec).model_dump(mode="json")
        # Evaluate every feature dimension before dispatching a kernel worker.
        normalize(validated)
        return self.store.insert("revision", {"project_id":project_id,"spec":validated,"parent_id":parent_id,"branch":branch,"status":"pending","report":None,"artifacts":[],"error":None,"proposal":proposal}, project_id)

    def new(self, name="Untitled design", family="enclosure", spec=None):
        validated = DesignSpec.model_validate(spec) if spec else recipe(family)
        self._validate_imports(validated.model_dump(mode='json'))
        validated.name = name
        project = self.store.insert("project", {"name":name,"recipe":validated.family,"active_revision_id":None,"history":[],"history_cursor":-1,"branch_heads":{}})
        revision = self._revision(project["id"], validated.model_dump(mode="json"))
        self.store.update(project["id"], branch_heads={"main":revision["id"]})
        job = self.jobs.submit(revision["id"],auto_accept=True)
        return {"project":project,"revision":revision,"job":job}

    @staticmethod
    def _convert_units(spec: dict, units: str):
        if units not in UNITS:
            raise ValueError("Unsupported unit")
        old = spec["units"]
        if old == units: return
        factor = UNITS[old]/UNITS[units]
        for parameter in spec["parameters"].values():
            if parameter.get("dimension","length") == "length":
                parameter["unit"] = parameter.get("unit") or old
        def convert(value,key=""):
            if key in TEXT_KEYS or key in NUMBER_KEYS or key in ANGLE_KEYS or key in {"direction","normal"}: return value
            if isinstance(value,dict): return {k:convert(v,k) for k,v in value.items()}
            if isinstance(value,list): return [convert(v,key) for v in value]
            if isinstance(value,bool): return value
            if isinstance(value,(float,int)): return value*factor
            # Explicit dimension constants prevent numeric-expression drift.
            if isinstance(value,str):
                try: return f"({float(value)})*{old}"
                except ValueError: return value
            return value
        for feature in spec["features"]: feature["parameters"]=convert(feature["parameters"])
        for part in spec["parts"]: part["transform"]["translation"]=convert(part["transform"]["translation"])
        for constraint in spec["constraints"]:
            constraint["parameters"]=convert(constraint["parameters"])
            constraint["tolerance"]*=factor
        for datum in spec["datums"].values():
            if isinstance(datum,dict) and "origin" in datum: datum["origin"]=convert(datum["origin"])
        spec["units"]=units

    def edit(self, project_id: str, changes: dict, protected=False):
        with self.lock:
            project = self.store.get(project_id,"project")
            base_id = changes.get("base_revision") or project["active_revision_id"]
            if not base_id: raise ValueError("Wait for the initial model to finish building")
            base = self.store.get(base_id,"revision")
            if base["project_id"] != project_id: raise ValueError("Revision belongs to another project")
            branch = str(changes.get("branch") or base["branch"])
            if not branch or len(branch)>80: raise ValueError("Invalid branch name")
            head = project.get("branch_heads",{}).get(branch)
            if branch == base["branch"] and base_id != project["active_revision_id"] and head != base_id:
                raise StaleRevision("Edit base is stale; select the current revision or create an explicit new branch")
            spec = deepcopy(changes.get("spec") or base["spec"])
            if "units" in changes: self._convert_units(spec,changes["units"])
            for key,value in changes.get("parameters",{}).items():
                if key not in spec["parameters"]: raise ValueError(f"Unknown parameter {key}")
                if isinstance(value,dict): spec["parameters"][key].update(value)
                else: spec["parameters"][key]["value"]=value
            features = {f["id"]:f for f in spec["features"]}
            for update in changes.get("update_features",[]):
                if update["id"] not in features: raise ValueError(f"Unknown feature {update['id']}")
                for key in ["name","inputs","roles"]:
                    if key in update: features[update["id"]][key]=update[key]
                if "parameters" in update: features[update["id"]]["parameters"].update(update["parameters"])
            removed = set(changes.get("remove_features",[]))
            if not removed.issubset(features): raise ValueError("Cannot remove unknown feature")
            for part in spec['parts']:
                if part['feature'] in removed:
                    output=features[part['feature']]
                    if len(output['inputs'])==1 and output['inputs'][0] not in removed:
                        part['feature']=output['inputs'][0]
                    else:
                        raise ValueError(f"Removing {output['id']} requires an explicit replacement part output")
            spec["features"] = [f for f in spec["features"] if f["id"] not in removed]
            for added in changes.get("add_features",[]):
                if added["id"] in features: raise ValueError("Feature ID already exists")
                spec["features"].append(added)
                for part in spec["parts"]:
                    if part["id"] == added["part"]: part["feature"]=added["id"]
            if "constraints" in changes and changes["constraints"] is not None:
                spec["constraints"] = changes["constraints"]
            if changes.get("new_constraints"):
                spec["constraints"].extend(changes["new_constraints"])
            if changes.get("assumptions"):
                spec["assumptions"].extend(changes["assumptions"])
            if protected:
                previous = {c["id"]:c for c in base["spec"]["constraints"] if c["required"]}
                current = {c["id"]:c for c in spec["constraints"]}
                for key,requirement in previous.items():
                    if current.get(key)!=requirement:
                        raise ValueError(f"Proposal changed hard requirement {key}. Revise it explicitly in the constraint inspector.")
                baseline={c['id']:c for c in normalize(base['spec'])['constraints'] if c['required']}
                proposed={c['id']:c for c in normalize(spec)['constraints']}
                preserve=set(changes.get('constraints_to_preserve',[]))
                for key,requirement in baseline.items():
                    # A requested envelope dimension can change; mounting/keep-out and
                    # supported wall contracts remain anchored to measured design intent.
                    if requirement['type']!='envelope' or key in preserve:
                        if proposed.get(key)!=requirement:
                            raise ValueError(f"Parameter changes implicitly alter preserved hard requirement {key}. Revise the requirement explicitly in the constraint inspector.")
            # Imported geometry is staged by import_reference; arbitrary paths are denied.
            self._validate_imports(spec)
            revision = self._revision(project_id,spec,base_id,branch,changes)
            heads = dict(project.get("branch_heads",{})); heads[branch]=revision["id"]
            self.store.update(project_id,branch_heads=heads)
            job = self.jobs.submit(revision["id"])
            return {"revision":revision,"job":job}

    def _validate_imports(self,spec):
        upload_root = (self.store.root/"imports").resolve()
        for feature in spec["features"]:
            if feature["type"]=="import_step":
                path = Path(feature["parameters"].get("path","")).resolve()
                if not path.is_relative_to(upload_root) or not path.is_file():
                    raise ValueError("Imported STEP must be uploaded through ShapeLoop-CAD")

    def accept(self, revision_id: str):
        with self.lock:
            revision = self.store.get(revision_id,"revision")
            if revision["status"] not in {"candidate","accepted"} or not revision.get("report") or revision["report"]["status"]!="PASS":
                raise ValueError("Only a fully verified candidate can be accepted")
            # Check immutable artifact integrity at acceptance; stale/swapped exports cannot pass.
            self.artifact(revision_id,"assembly.step",verify_all=True)
            project = self.store.get(revision["project_id"],"project")
            if project["active_revision_id"] == revision_id: return revision
            history = list(project["history"][:project["history_cursor"]+1]); history.append(revision_id)
            heads=dict(project.get("branch_heads",{})); heads[revision["branch"]]=revision_id
            self.store.update(project["id"],active_revision_id=revision_id,history=history,history_cursor=len(history)-1,branch_heads=heads)
            return self.store.update(revision_id,status="accepted")

    def reject(self, revision_id):
        revision=self.store.get(revision_id,"revision")
        project=self.store.get(revision["project_id"],"project")
        if project["active_revision_id"]==revision_id: raise ValueError("Undo before rejecting the active revision")
        if revision["status"]=="building": raise ValueError("Cancel the job before rejecting")
        return self.store.update(revision_id,status="rejected")

    def history(self, project_id, direction):
        with self.lock:
            project=self.store.get(project_id,"project")
            cursor=project["history_cursor"]+(-1 if direction=="undo" else 1)
            if not 0 <= cursor < len(project["history"]): raise ValueError(f"No revision to {direction}")
            self.store.update(project_id,history_cursor=cursor,active_revision_id=project["history"][cursor])
            return self.project(project_id)

    def compare(self,project_id,a,b):
        ra,rb=self.store.get(a,"revision"),self.store.get(b,"revision")
        if any(r["project_id"]!=project_id for r in [ra,rb]): raise ValueError("Revision belongs to another project")
        pa,pb=ra["spec"]["parameters"],rb["spec"]["parameters"]
        fa,fb={f["id"]:f for f in ra["spec"]["features"]},{f["id"]:f for f in rb["spec"]["features"]}
        changes=[{"parameter":k,"from":pa.get(k),"to":pb.get(k)} for k in sorted(set(pa)|set(pb)) if pa.get(k)!=pb.get(k)]
        changed=[k for k in set(fa)|set(fb) if fa.get(k)!=fb.get(k)]
        # Parameter dependency changes can affect feature geometry without changing source records.
        na,nb=normalize(ra["spec"]),normalize(rb["spec"])
        nfa,nfb={f["id"]:f for f in na["features"]},{f["id"]:f for f in nb["features"]}
        affected=[k for k in set(nfa)|set(nfb) if nfa.get(k)!=nfb.get(k)]
        return {"from":a,"to":b,"frame":"world / millimeters","parameters":changes,"changed_features":sorted(set(changed)|set(affected)),"preserved_features":sorted(k for k in set(fa)&set(fb) if k not in changed and k not in affected),"reports":{"from":ra.get("report"),"to":rb.get("report")}}

    def artifact(self,revision_id,filename,verify_all=False):
        revision=self.store.get(revision_id,"revision")
        if Path(filename).name!=filename or filename not in revision.get("artifacts",[]): raise KeyError("Artifact not found")
        root=(self.store.root/"artifacts"/revision_id).resolve()
        path=(root/filename).resolve()
        if not path.is_relative_to(root) or not path.is_file(): raise KeyError("Artifact not found")
        for name,digest in revision.get('artifact_hashes',{}).items():
            if verify_all or name==filename:
                source=root/name
                if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                    raise ValueError(f'Export integrity mismatch: {name}; rebuild this revision')
        manifest_path=root/"manifest.json"
        if manifest_path.exists():
            manifest=json.loads(manifest_path.read_text())
            expected=hashlib.sha256(json.dumps(revision["spec"],sort_keys=True).encode()).hexdigest()
            if manifest["revision_id"]!=revision_id or manifest["spec_sha256"]!=expected: raise ValueError("Export revision identity mismatch")
            for name,digest in manifest["files"].items():
                if verify_all or name==filename:
                    source=root/name
                    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                        raise ValueError(f"Export integrity mismatch: {name}; rebuild this revision")
        return path

    def import_reference(self,name,content,kind="step"):
        if kind not in {"step","stl"}: raise ValueError("Only STEP and STL reference inputs are supported")
        if len(content)>32*1024**2: raise ValueError("Import exceeds 32 MB limit")
        import uuid
        root=self.store.root/"imports"; root.mkdir(exist_ok=True)
        path=root/f"{uuid.uuid4().hex}.{kind}"
        path.write_bytes(content)
        if kind=="stl":
            return self.store.insert("reference",{"name":name,"kind":"mesh_reference","path":str(path),"editable":False,"note":"STL is a mesh reference; no feature history or solid constraints are recovered."})
        spec={"name":name,"family":"imported","units":"mm","parts":[{"id":"reference","name":name,"feature":"imported_shape"}],"features":[{"id":"imported_shape","name":"Direct STEP geometry","type":"import_step","part":"reference","parameters":{"path":str(path)}}],"assumptions":["Direct geometry imported from STEP; original feature history is unavailable."]}
        return self.new(name,"imported",spec)

    def context(self,revision_id):
        revision=self.store.get(revision_id,"revision")
        project=self.store.get(revision["project_id"],"project")
        originals=[]; ancestor=revision; seen=set()
        while ancestor and ancestor['id'] not in seen:
            seen.add(ancestor['id']); proposal=ancestor.get('proposal') or {}
            if proposal.get('original_instruction'): originals.append(proposal['original_instruction'])
            ancestor=self.store.get(ancestor['parent_id'],'revision') if ancestor.get('parent_id') else None
        return {"design_spec":revision["spec"],"named_features":revision['spec']['features'],"constraints":revision['spec']['constraints'],"units":revision['spec']['units'],"active_revision":project["active_revision_id"],"base_revision":revision_id,"branch_state":project["branch_heads"],"measured_results":revision.get("report"),"unresolved_decisions":revision["spec"].get("assumptions",[]),"original_instruction":revision.get("proposal",{}),'original_instructions':list(reversed(originals))}

    def check(self,revision_id):
        # A new verification process reopens actual files, never just stored parameter labels.
        revision=self.store.get(revision_id,"revision")
        path=self.artifact(revision_id,"assembly.step",verify_all=True)
        import subprocess,sys,tempfile
        with tempfile.TemporaryDirectory(prefix="shapeloop-check-") as temporary:
            request=Path(temporary)/"request.json"; result=Path(temporary)/"result.json"
            reopened=Path(temporary)/'artifacts'; reopened.mkdir()
            for file in path.parent.iterdir():
                if file.suffix=='.step' or file.name=='metadata.json': shutil.copy2(file,reopened/file.name)
            request.write_text(json.dumps({"spec":revision["spec"],"output_dir":str(reopened),"limits":self.settings.value["workers"]}))
            process=subprocess.run([sys.executable,"-m","shapeloop.worker","verify",str(request),str(result)],capture_output=True,timeout=self.settings.value["workers"]["timeout_seconds"])
            if not result.exists(): raise ValueError("Verification process failed without a result")
            data=json.loads(result.read_text())
            if not data["ok"]: raise ValueError(data["error"])
            return data["result"]

    def measure(self,revision_id,entities,kind='distance'):
        if not isinstance(entities,list) or not 1<=len(entities)<=2 or not all(isinstance(e,str) and len(e)<200 for e in entities):
            raise ValueError('Select one or two revision-local face IDs')
        if kind not in {'distance','angle','area'}: raise ValueError('Unsupported measurement')
        path=self.artifact(revision_id,'mesh.json',verify_all=True)
        import subprocess,sys,tempfile
        with tempfile.TemporaryDirectory(prefix='shapeloop-measure-') as temporary:
            request=Path(temporary)/'request.json'; result=Path(temporary)/'result.json'
            request.write_text(json.dumps({'output_dir':str(path.parent),'entities':entities,'kind':kind,'limits':self.settings.value['workers']}))
            subprocess.run([sys.executable,'-m','shapeloop.worker','measure',str(request),str(result)],capture_output=True,timeout=self.settings.value['workers']['timeout_seconds'])
            if not result.exists(): raise ValueError('Measurement worker failed without a result')
            data=json.loads(result.read_text())
            if not data['ok']: raise ValueError(data['error'])
            measured=data['result']; self.store.insert('measurement',{'revision_id':revision_id,**measured},self.store.get(revision_id,'revision')['project_id'])
            return measured

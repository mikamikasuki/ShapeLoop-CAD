"""CLI entry points call the same domain services as the workbench."""
from __future__ import annotations
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
import typer
from .service import Service
from .store import data_directory

app=typer.Typer(help="ShapeLoop-CAD local parametric CAD workbench",no_args_is_help=True)
scout_app=typer.Typer(help="Source-grounded CAD knowledge")
app.add_typer(scout_app,name="scout")

def output(data): typer.echo(json.dumps(data,indent=2,ensure_ascii=False,default=str))

@contextmanager
def domain(root=None):
    service=Service(root)
    try: yield service
    except (ValueError,KeyError,RuntimeError,TimeoutError,subprocess.SubprocessError) as error:
        typer.echo(str(error),err=True); raise typer.Exit(1)
    finally: service.close()

def pointer(project: Path):
    path=project/"shapeloop-project.json" if project.is_dir() else project
    if not path.is_file(): raise typer.BadParameter("Project pointer not found; create it with shapeloop-cad new --project PATH")
    try: value=json.loads(path.read_text())
    except (ValueError,OSError) as error: raise typer.BadParameter('Invalid ShapeLoop-CAD project pointer') from error
    if not {"project_id","data_directory"}.issubset(value): raise typer.BadParameter("Invalid ShapeLoop-CAD project pointer")
    return value

def active(service,id):
    project=service.project(id)
    return project.get("active_revision_id") or project["revisions"][-1]["id"]

def wait_candidate(service,result,accept=False):
    job=service.jobs.wait(result["job"]["id"])
    if job["status"]=="succeeded" and accept: service.accept(result["revision"]["id"])
    return {"revision_id":result["revision"]["id"],"job":job,"revision":service.store.get(result["revision"]["id"],"revision")}

@app.command()
def doctor():
    """Actually build/export/reimport a primitive in an isolated process."""
    from .scout import installed_versions
    code="""import cadquery as cq,json,sys
from pathlib import Path
p=Path(sys.argv[1]); a=cq.Workplane('XY').box(12,8,4).faces('>Z').workplane().hole(2).val()
cq.exporters.export(a,str(p)); b=cq.importers.importStep(str(p)).val()
delta=abs(a.Volume()-b.Volume()); valid=b.isValid() and len(b.Solids())==1 and delta<1e-6
print(json.dumps({'valid':valid,'solid_count':len(b.Solids()),'volume_mm3':b.Volume(),'volume_delta_mm3':delta,'step_bytes':p.stat().st_size}))
raise SystemExit(0 if valid else 1)
"""
    with tempfile.TemporaryDirectory(prefix="shapeloop-doctor-") as temp:
        result=subprocess.run([sys.executable,"-c",code,str(Path(temp)/"primitive.step")],capture_output=True,text=True,timeout=120)
        if result.returncode:
            output({"ok":False,"error":result.stderr[-1500:]}); raise typer.Exit(1)
        output({"ok":True,"platform":platform.platform(),"machine":platform.machine(),"versions":installed_versions(),"primitive":json.loads(result.stdout),"frontend_bundled":(Path(__file__).parent/"static/index.html").is_file()})

@app.command()
def serve(host:str="127.0.0.1",port:int=8765,data_dir:Path|None=None):
    """Launch the local backend and bundled workbench."""
    if host not in {"127.0.0.1","localhost","::1","0.0.0.0"}: raise typer.BadParameter("Choose a loopback host or container 0.0.0.0")
    import uvicorn
    from .api import create_app
    uvicorn.run(create_app(data_dir),host=host,port=port,log_level="info")

@app.command()
def new(recipe:str="enclosure",name:str="",project:Path|None=None):
    with domain() as service:
        result=service.new(name or recipe.title(),recipe)
        completed=wait_candidate(service,result,True)
        directory=(project or (service.store.root/"projects"/result["project"]["id"])).resolve()
        directory.mkdir(parents=True,exist_ok=True)
        (directory/"shapeloop-project.json").write_text(json.dumps({"project_id":result["project"]["id"],"data_directory":str(service.store.root)},indent=2))
        output({"project":str(directory),"project_id":result["project"]["id"],"revision_id":completed["revision_id"],"status":completed["job"]["status"],"report":completed["revision"].get("report"),"exports":str(service.store.root/"artifacts"/completed["revision_id"])})
        if completed["job"]["status"]!="succeeded": raise typer.Exit(1)

@app.command()
def build(project:Annotated[Path,typer.Option('--project')],accept:bool=False):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service:
        base=active(service,p["project_id"])
        revision=service.store.get(base,"revision")
        result=service.edit(p["project_id"],{"base_revision":base}) if revision.get("artifacts") else {"revision":revision,"job":service.jobs.submit(base)}
        completed=wait_candidate(service,result,accept); output(completed)
        if completed["job"]["status"]!="succeeded": raise typer.Exit(1)

@app.command()
def edit(project:Annotated[Path,typer.Option('--project')],instruction:str="",set_:Annotated[list[str]|None,typer.Option("--set",help="Explicit NAME=VALUE change; repeatable")]=None,feature_json:Path|None=None,constraints:Path|None=None,branch:str="",accept:bool=False):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service:
        base=active(service,p["project_id"])
        if instruction:
            from .provider import ProviderClient
            config=dict(service.settings.value["provider"]); config["max_output_tokens"]=config.pop("max_tokens")
            changes=ProviderClient(config).edit(instruction,base,service.context(base)).model_dump(mode="json",exclude_none=True)
        else: changes={"base_revision":base,"parameters":{}}
        for item in set_ or []:
            if "=" not in item: raise ValueError("--set uses NAME=VALUE")
            key,value=item.split("=",1)
            try: parsed=json.loads(value)
            except ValueError: parsed=value
            changes.setdefault("parameters",{})[key]=parsed
        if feature_json: changes.update(json.loads(feature_json.read_text()))
        if constraints: changes["constraints"]=json.loads(constraints.read_text())
        if branch: changes["branch"]=branch
        completed=wait_candidate(service,service.edit(p["project_id"],changes,protected=bool(instruction)),accept)
        output(completed)
        if completed["job"]["status"]!="succeeded": raise typer.Exit(1)

@app.command()
def check(project:Annotated[Path,typer.Option('--project')],revision:str=""):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service:
        report=service.check(revision or active(service,p["project_id"])); output(report)
        if report["status"]!="PASS": raise typer.Exit(1)

@app.command(name="export")
def export_file(project:Annotated[Path,typer.Option('--project')],format:str="step",revision:str="",output_path:Annotated[Path|None,typer.Option("--output")]=None):
    names={"step":"assembly.step","stl":"assembly.stl","svg":"assembly.svg","source":"design.py","spec":"design.json","report":"report.json","bundle":"bundle.zip"}
    if format not in names: raise typer.BadParameter("Choose step, stl, svg, source, spec, report, or bundle")
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service:
        rid=revision or active(service,p["project_id"]); source=service.artifact(rid,names[format],verify_all=True)
        if output_path:
            output_path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,output_path); source=output_path.resolve()
        output({"revision_id":rid,"format":format,"units":"mm","path":str(source)})

@app.command()
def compare(project:Annotated[Path,typer.Option('--project')],from_:Annotated[str,typer.Option("--from")],to:Annotated[str,typer.Option("--to")]):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service: output(service.compare(p["project_id"],from_,to))

@app.command()
def accept(project:Annotated[Path,typer.Option('--project')],revision:Annotated[str,typer.Option('--revision')]):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service: output(service.accept(revision))

@app.command()
def undo(project:Annotated[Path,typer.Option('--project')]):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service: output(service.history(p["project_id"],"undo"))

@app.command()
def redo(project:Annotated[Path,typer.Option('--project')]):
    p=pointer(project)
    with domain(Path(p["data_directory"])) as service: output(service.history(p["project_id"],"redo"))

@app.command()
def demo(output_dir:Path|None=None):
    """Run the real sequential enclosure/plate/bracket acceptance workflow."""
    from .evaluation import run_demo
    directory=output_dir or data_directory()/"evaluation"/"demo"
    output(run_demo(directory))

@app.command()
def benchmark(output_dir:Path|None=None,sequences:int=15):
    """Generate structured comparison sequences and actual geometry measurements."""
    from .evaluation import benchmark as run
    output(run(output_dir or data_directory()/"evaluation"/"benchmark",sequences))

def scout_service():
    from .scout import SolutionScout,ScoutSettings,DEFAULT_SOURCES
    from .config import Settings
    root=data_directory(); root.mkdir(parents=True,exist_ok=True)
    values=dict(Settings(root).value["scout"]); values["sources"]=values["sources"] or DEFAULT_SOURCES
    return SolutionScout(root/"scout.sqlite",ScoutSettings.model_validate(values))

@scout_app.command()
def sync(network:bool=False):
    scout=scout_service()
    if network: scout.settings.network_enabled=True
    output(scout.sync())

@scout_app.command()
def ask(operation:str,error:str="",network:bool=False,reproduce:bool=True):
    scout=scout_service()
    if network: scout.settings.network_enabled=True
    result=scout.ask({"operation":operation,"error":error,"reproduce":reproduce})
    from .scout_reasoning import reason_over_sources
    from .config import Settings
    from .provider import ProviderClient
    config=dict(Settings(data_directory()).value['provider']); config['max_output_tokens']=config.pop('max_tokens')
    output(reason_over_sources(scout,result,ProviderClient(config)))

@scout_app.command()
def status(): output(scout_service().status())

@scout_app.command()
def watch(network:bool=False,interval:int=3600):
    """Refresh selected references until interrupted; Ctrl+C stops safely."""
    scout=scout_service(); scout.settings.network_enabled=network or scout.settings.network_enabled
    scout.settings.interval_seconds=interval
    output(scout.start_watch())
    import time
    try:
        while True: time.sleep(.5)
    except KeyboardInterrupt: output(scout.stop_watch())

if __name__=="__main__": app()

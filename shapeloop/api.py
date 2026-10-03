"""Loopback HTTP boundary for the shared ShapeLoop-CAD services."""
from __future__ import annotations
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .service import Service, StaleRevision
from .provider import ProviderClient, ProviderConfig, ProviderError, EditProposal
from .scout import SolutionScout, ScoutSettings, ScoutStore, DEFAULT_SOURCES, installed_versions

def create_app(root: Path | None = None) -> FastAPI:
    service = Service(root)
    token = secrets.token_urlsafe(32)
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()
    app = FastAPI(title="ShapeLoop-CAD", version="0.1.0", lifespan=lifespan)
    app.state.service = service
    app.state.token = token

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        host = request.url.hostname
        if host not in {"localhost","127.0.0.1","::1","testserver"}:
            return JSONResponse({"detail":"ShapeLoop-CAD accepts loopback requests only"},status_code=403)
        origin = request.headers.get("origin")
        if origin:
            expected = urlsplit(str(request.url))
            parsed = urlsplit(origin)
            same = (parsed.scheme,parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80)) == (expected.scheme,expected.hostname,expected.port or (443 if expected.scheme=="https" else 80))
            if not same:
                return JSONResponse({"detail":"Cross-origin access is denied"},status_code=403)
        if request.url.path.startswith("/api/") and request.method not in {"GET","HEAD","OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("X-ShapeLoop-Token",""),token):
                return JSONResponse({"detail":"Invalid local session token; reload the app"},status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="same-origin"
        response.headers["Cache-Control"]="no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.exception_handler(KeyError)
    async def missing(request,error): return JSONResponse({"detail":str(error)},status_code=404)
    @app.exception_handler(StaleRevision)
    async def stale(request,error): return JSONResponse({"detail":str(error)},status_code=409)
    @app.exception_handler(ValueError)
    async def invalid(request,error): return JSONResponse({"detail":str(error)},status_code=422)
    @app.exception_handler(ProviderError)
    async def provider_failure(request,error): return JSONResponse({"detail":str(error)},status_code=503)

    def provider():
        data=dict(service.settings.value["provider"])
        data["max_output_tokens"]=data.pop("max_tokens")
        return ProviderClient(ProviderConfig.model_validate(data))

    def scout():
        settings=dict(service.settings.value["scout"])
        if not settings["sources"]: settings["sources"]=DEFAULT_SOURCES
        validated=ScoutSettings.model_validate(settings)
        if service._scout is None:
            service._scout=SolutionScout(ScoutStore(service.store.root/"scout.sqlite"),validated)
        else:
            service._scout.settings=validated
        return service._scout

    @app.get("/api/session")
    def session(): return {"token":token,"version":"0.1.0","units":"mm"}
    @app.get("/api/health")
    def health(): return {"status":"ok","versions":installed_versions(),"data_directory":str(service.store.root)}
    @app.get("/api/recipes")
    def recipes():
        from .recipes import recipe
        return [recipe(name).model_dump(mode="json") for name in ["enclosure","plate","bracket"]]
    import threading
    thumbnail_lock=threading.Lock()
    @app.get('/api/recipes/{name}/thumbnail.svg')
    def recipe_thumbnail(name:str):
        from .recipes import recipe
        import hashlib,subprocess,sys
        spec=recipe(name).model_dump(mode='json')
        digest=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:16]
        folder=service.store.root/'thumbnails'/f'{name}-{digest}'
        with thumbnail_lock:
            if not (folder/'assembly.svg').exists():
                folder.mkdir(parents=True,exist_ok=True)
                request=folder/'request.json'; result=folder/'build-result.json'
                request.write_text(json.dumps({'spec':spec,'output_dir':str(folder),'limits':service.settings.value['workers']}))
                process=subprocess.run([sys.executable,'-m','shapeloop.worker','build',str(request),str(result)],capture_output=True,timeout=service.settings.value['workers']['timeout_seconds'])
                if not result.exists() or not json.loads(result.read_text()).get('ok'):
                    raise ValueError('Could not build the recipe thumbnail')
        return FileResponse(folder/'assembly.svg',media_type='image/svg+xml')
    @app.get("/api/projects")
    def projects(): return service.projects()
    @app.post("/api/projects")
    def new(body:dict): return service.new(body.get("name","Untitled design"),body.get("recipe","enclosure"),body.get("spec"))
    @app.get("/api/projects/{id}")
    def project(id:str): return service.project(id)
    @app.patch("/api/projects/{id}")
    def rename(id:str,body:dict):
        name=str(body.get("name","")).strip()
        if not name or len(name)>200: raise ValueError("Project name must contain 1–200 characters")
        return service.store.update(id,name=name)
    @app.post("/api/projects/{id}/edit")
    def edit(id:str,body:dict): return service.edit(id,body)
    @app.post("/api/projects/{id}/undo")
    def undo(id:str): return service.history(id,"undo")
    @app.post("/api/projects/{id}/redo")
    def redo(id:str): return service.history(id,"redo")
    @app.get("/api/projects/{id}/compare")
    def compare(id:str,request:Request):
        a,b=request.query_params.get("from"),request.query_params.get("to")
        if not a or not b: raise ValueError("Specify from and to revision IDs")
        return service.compare(id,a,b)
    @app.get("/api/revisions/{id}")
    def revision(id:str): return service.store.get(id,"revision")
    @app.get("/api/revisions/{id}/measurements")
    def measurements(id:str): return service.store.get(id,"revision").get("report")
    @app.post('/api/revisions/{id}/measure')
    def measure(id:str,body:dict): return service.measure(id,body.get('entities'),body.get('kind','distance'))
    @app.post("/api/revisions/{id}/build")
    def build(id:str): return service.jobs.submit(id)
    @app.post("/api/revisions/{id}/check")
    def check(id:str): return service.check(id)
    @app.post("/api/revisions/{id}/accept")
    def accept(id:str): return service.accept(id)
    @app.post("/api/revisions/{id}/reject")
    def reject(id:str): return service.reject(id)
    @app.get("/api/jobs")
    def jobs(): return service.store.list("job")
    @app.get("/api/jobs/{id}")
    def job(id:str): return service.store.get(id,"job")
    @app.get("/api/jobs/{id}/events")
    def events(id:str,after:int=0): return service.store.events(id,after)
    @app.post("/api/jobs/{id}/cancel")
    def cancel(id:str): return service.jobs.cancel(id)
    @app.post("/api/jobs/{id}/retry")
    def retry(id:str):
        old=service.store.get(id,"job")
        if old["status"] not in {"failed","cancelled","interrupted"}: raise ValueError("Only unfinished or failed jobs can be retried")
        return service.jobs.submit(old["revision_id"])
    @app.get("/api/artifacts/{revision_id}/{filename}")
    def artifact(revision_id:str,filename:str):
        path=service.artifact(revision_id,filename)
        return FileResponse(path, filename=filename if path.suffix in {".step",".stl",".zip",".py",".svg"} else None)
    @app.get("/api/settings")
    def settings():
        data=service.settings.public(); data["scout"]["sources"]=data["scout"]["sources"] or DEFAULT_SOURCES
        data["data_directory"]=str(service.store.root)
        return data
    @app.put("/api/settings")
    def save_settings(body:dict):
        if "provider" in body:
            data={**service.settings.value["provider"],**body["provider"]}
            data.pop("configured",None); data.pop("has_api_key",None)
            data["max_output_tokens"]=data.pop("max_tokens")
            ProviderConfig.model_validate(data)
        if "scout" in body: ScoutSettings.model_validate({**service.settings.value["scout"],**body["scout"]})
        result=service.settings.update(body)
        result["note"]="Worker concurrency changes apply after server restart; other limits apply to the next operation."
        return result
    @app.post("/api/provider/probe")
    def probe(): return provider().probe()
    @app.get("/api/provider/models")
    def models(): return provider().discover_models()
    @app.post("/api/generate")
    def generate(body:dict):
        instruction=str(body.get("instruction", "")).strip()
        if not instruction: raise ValueError("Enter a generation instruction")
        client=provider(); spec=client.generate(instruction)
        result=service.new(body.get("name") or spec.name,spec.family,spec.model_dump(mode="json"))
        service.store.update(result["revision"]["id"],proposal={"original_instruction":instruction,"provider_usage":client.last_call})
        return result
    @app.post("/api/projects/{id}/propose")
    def propose(id:str,body:dict):
        project=service.project(id); base=body.get("base_revision") or project["active_revision_id"]
        if not base: raise ValueError("No accepted base revision")
        if service.store.get(base,"revision")["project_id"]!=id: raise ValueError("Wrong project")
        client=provider(); proposal=client.edit(body["instruction"],base,service.context(base))
        record=service.store.insert("proposal",{"project_id":id,"proposal":proposal.model_dump(mode="json"),"instruction":body["instruction"],"usage":client.last_call},id)
        return {**proposal.model_dump(mode="json"),"proposal_id":record["id"],"usage":client.last_call}
    @app.post("/api/projects/{id}/apply-proposal")
    def apply_proposal(id:str,body:dict):
        data=body.get("proposal",body); data=dict(data); proposal_id=data.pop("proposal_id",None); data.pop("usage",None)
        validated=EditProposal.model_validate(data)
        record=service.store.get(proposal_id,'proposal') if proposal_id else None
        if record and record['project_id']!=id: raise ValueError('Proposal belongs to another project')
        changes=validated.model_dump(mode='json',exclude_none=True)
        if record:
            changes['original_instruction']=record['instruction']
            changes['proposal_id']=record['id']
        return service.edit(id,changes,protected=True)
    @app.post("/api/projects/{id}/repair")
    def repair(id:str,body:dict):
        project=service.project(id)
        failed=service.store.get(body['failed_revision'],'revision')
        if failed['project_id']!=id: raise ValueError('Revision belongs to another project')
        if failed['status'] not in {'failed','cancelled','interrupted'}: raise ValueError('Select a failed candidate to repair')
        attempts=max(1,min(3,int(body.get('attempts',2))))
        client=provider()
        if not client.config.configured: raise ProviderError('Configure an endpoint and model before requesting a repair')
        base=project['active_revision_id']
        if not base: raise ValueError('A verified accepted base is required for repair')
        counterexamples=(failed.get('report') or {}).get('measurements',[])
        counterexamples=[m for m in counterexamples if m['status']!='PASS']
        solutions=[]
        if body.get('consult_scout',True):
            operation=str(body.get('operation') or 'boolean')
            guidance=scout().ask({'operation':operation,'error':str(failed.get('error') or ''),'feature_graph':failed['spec']['features'],'geometry':{'family':failed['spec']['family']},'invariants':failed['spec']['constraints'],'budget':{'max_fetches':2,'max_reproductions':1,'max_seconds':15}})
            solutions=guidance.get('cards',[])
        outcomes=[]
        for attempt in range(attempts):
            context=service.context(base)
            context.update(failed_candidate=failed['spec'],counterexamples=counterexamples,solution_cards=solutions,previous_repairs=outcomes)
            instruction=str(body.get('instruction') or (failed.get('proposal') or {}).get('original_instruction') or 'Repair the failed candidate while completing its requested changes.')
            try:
                proposal=client.edit(instruction+' Propose a narrower local repair. Never remove or relax hard requirements. A failed bounded search is not a proof of infeasibility.',base,context)
                changes=proposal.model_dump(mode='json',exclude_none=True)
                changes['branch']=f'repair-{failed["id"][:6]}-{attempt+1}'
                candidate=service.edit(id,changes,protected=True)
                job=service.jobs.wait(candidate['job']['id'])
                revision=service.store.get(candidate['revision']['id'],'revision')
                report=revision.get('report') or {'status':'UNKNOWN','measurements':[]}
                hard_failures=sum(m['status']!='PASS' for m in report['measurements'] if m.get('required',True))
                outcomes.append({'revision_id':revision['id'],'job_id':job['id'],'status':job['status'],'hard_failures':hard_failures,'proposal':changes,'usage':client.last_call,'report':report})
                if job['status']=='succeeded': break
                failed=revision
                counterexamples=[m for m in report['measurements'] if m['status']!='PASS']
            except (ValueError,ProviderError) as error:
                outcomes.append({'status':'rejected_proposal','error':str(error),'usage':client.last_call})
        successful=[o for o in outcomes if o.get('status')=='succeeded']
        result={'attempts':outcomes,'selected_revision':successful[0]['revision_id'] if successful else None,'accepted':False,'unresolved':[] if successful else ['No verified repair within this budget; acceptance requirements remain unchanged.'],'solution_cards':solutions}
        service.store.insert('repair',result,id)
        return result
    @app.get("/api/scout/status")
    def scout_status(): return scout().status()
    @app.get("/api/scout/cards")
    def scout_cards(): return scout().cards()
    @app.post("/api/scout/sync")
    def scout_sync(body:dict|None=None): return scout().sync(budget=(body or {}).get("budget"),sources=(body or {}).get("sources"))
    @app.post("/api/scout/ask")
    def scout_ask(body:dict):
        engine=scout(); result=engine.ask(body)
        from .scout_reasoning import reason_over_sources
        calls=(body.get('budget') or {}).get('model_calls',1)
        return reason_over_sources(engine,result,provider(),calls,allow_private_context=body.get('allow_private_query') is True,request=body)
    @app.post("/api/scout/watch")
    def scout_watch(): return scout().start_watch()
    @app.post("/api/scout/stop")
    def scout_stop(): return scout().stop_watch()
    @app.post("/api/scout/cancel")
    def scout_cancel(): return scout().cancel()
    @app.post("/api/scout/clear")
    def scout_clear(body:dict|None=None):
        scout().store.clear(sources=(body or {}).get("sources",False)); return {"cleared":True}
    @app.post("/api/imports")
    async def upload(file:UploadFile=File(...)):
        extension=Path(file.filename or "").suffix.lower()
        if extension not in {".step",".stp",".stl"}: raise ValueError("Choose a STEP or STL file")
        content=await file.read(32*1024**2+1)
        return service.import_reference(Path(file.filename or "Reference").stem,content,"stl" if extension==".stl" else "step")
    @app.get('/api/references')
    def references(): return [{k:v for k,v in r.items() if k!='path'} for r in service.store.list('reference')]
    @app.get('/api/references/{id}/file')
    def reference_file(id:str):
        record=service.store.get(id,'reference'); path=Path(record['path']).resolve()
        if not path.is_relative_to((service.store.root/'imports').resolve()) or not path.is_file(): raise KeyError('Reference missing')
        return FileResponse(path,filename=f"{record['name']}.stl")
    @app.post('/api/storage/cleanup')
    def cleanup(body:dict|None=None):
        import shutil
        removed=[]
        for job in service.store.list('job'):
            if job['status'] in {'succeeded','failed','cancelled','interrupted'}:
                scratch=service.store.root/'jobs'/job['id']
                if scratch.exists(): shutil.rmtree(scratch); removed.append(job['id'])
        if (body or {}).get('scout_cache'): scout().store.clear(sources=True)
        return {'removed_job_directories':len(removed),'projects_preserved':len(service.projects())}

    static=Path(__file__).parent/"static"
    dev=Path(__file__).parent.parent/"frontend"/"dist"
    assets=static if (static/"index.html").exists() else dev
    if (assets/"assets").exists(): app.mount("/assets",StaticFiles(directory=assets/"assets"),name="assets")
    if (assets/'licenses').exists(): app.mount('/licenses',StaticFiles(directory=assets/'licenses'),name='licenses')
    @app.get('/THIRD_PARTY_NOTICES.md')
    def notices():
        path=assets/'THIRD_PARTY_NOTICES.md'
        if not path.is_file():path=Path(__file__).parent.parent/'THIRD_PARTY_NOTICES.md'
        if not path.is_file():raise HTTPException(404,'Notices unavailable')
        return FileResponse(path,media_type='text/plain')
    @app.get("/{path:path}")
    def frontend(path:str):
        if path.startswith("api/"): raise HTTPException(404,"Unknown API route")
        if not (assets/"index.html").exists():
            return JSONResponse({"detail":"Frontend assets missing. Run npm ci && npm run build in frontend, then scripts/package_frontend.py."},status_code=503)
        return FileResponse(assets/"index.html")
    return app

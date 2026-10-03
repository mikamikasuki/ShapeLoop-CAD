"""Actual structured workflows and measured, explicitly non-model comparisons."""
from __future__ import annotations
import copy
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .service import Service
from .recipes import recipe
from .spec import normalize
from .verifier import analytic_conflicts


def _wait(service, submitted, accept=True):
    job=service.jobs.wait(submitted['job']['id'],timeout=180)
    rid=submitted['revision']['id']
    revision=service.store.get(rid,'revision')
    if job['status']=='succeeded' and accept:
        revision=service.accept(rid)
    return {'revision_id':rid,'job_id':job['id'],'job_status':job['status'],'status':revision['status'],'report':revision.get('report'),'error':revision.get('error'),'duration_seconds':job.get('duration_seconds')}


def _require_pass(result):
    if result['job_status']!='succeeded' or result['report']['status']!='PASS':
        raise RuntimeError(f"Workflow failed: {json.dumps(result,default=str)}")
    return result


def _slot(id,part,input,size,center):
    return {'id':id,'name':id.replace('_',' ').title(),'type':'slot','part':part,'inputs':[input],'parameters':{'size':size,'center':center},'roles':['cutout']}


def _write_report(directory,name,result):
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/name
    result['report_path']=str(path.resolve())
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False))
    return result


def run_demo(output_dir):
    """Enclosure acceptance sequence, restart/rebuild, plus genuine plate/bracket edits."""
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    service=Service(out/'state');events=[];started=time.monotonic()
    try:
        submitted=service.new('ShapeLoop-CAD acceptance enclosure','enclosure');pid=submitted['project']['id']
        initial=_require_pass(_wait(service,submitted));events.append({'operation':'initial enclosure including separate lid',**initial})
        rid=initial['revision_id']
        initial_holes=next(m['actual'] for m in initial['report']['measurements'] if m['id']=='mounting_pattern')
        submitted=service.edit(pid,{'base_revision':rid,'parameters':{'height':24}})
        reduced=_require_pass(_wait(service,submitted));rid=reduced['revision_id'];events.append({'operation':'reduce height to24; preserve mounting datum positions and diameters',**reduced})
        reduced_holes=next(m['actual'] for m in reduced['report']['measurements'] if m['id']=='mounting_pattern')
        if reduced_holes['centers']!=initial_holes['centers'] or reduced_holes['diameters']!=initial_holes['diameters']:
            raise RuntimeError('Measured mounting pattern changed during height edit')
        feature=_slot('connector','body','body_edges',[12,6,8],[0,-25,12])
        added=_require_pass(_wait(service,service.edit(pid,{'base_revision':rid,'add_features':[feature]})));rid=added['revision_id'];events.append({'operation':'add connector cutout',**added})
        moved=_require_pass(_wait(service,service.edit(pid,{'base_revision':rid,'update_features':[{'id':'connector','parameters':{'center':[12,-25,12]}}]})));rid=moved['revision_id'];events.append({'operation':'move connector cutout along front wall',**moved})
        filleted=_require_pass(_wait(service,service.edit(pid,{'base_revision':rid,'parameters':{'fillet_radius':1}})));rid=filleted['revision_id'];events.append({'operation':'change supported outer vertical fillet from0.8 to1mm',**filleted})
        vents=[_slot(f'vent_{i}','body','connector' if i==0 else f'vent_{i-1}',[3,6,7],[-20+i*6,25,13]) for i in range(4)]
        vented=_require_pass(_wait(service,service.edit(pid,{'base_revision':rid,'add_features':vents})));rid=vented['revision_id'];main=rid;events.append({'operation':'add four vents away from component keep-out',**vented})
        alternative=_slot('lid_vent','lid','lid_holes',[12,3,6],[0,0,23])
        branched=_require_pass(_wait(service,service.edit(pid,{'base_revision':rid,'branch':'alternative-lid','add_features':[alternative]})));rid=branched['revision_id'];events.append({'operation':'branch alternative vented lid',**branched})
        comparison=service.compare(pid,main,rid)
        conflict_constraint={'id':'oversize_component','name':'Fixed35mm internal component','type':'internal_clearance','required':True,'features':['body_cavity'],'parameters':{'part':'body','size':[40,20,35],'center':[0,0,19.5],'minimum':1,'max_volume':.001},'tolerance':.01}
        contradictory=service.edit(pid,{'base_revision':rid,'new_constraints':[conflict_constraint]})
        failed=_wait(service,contradictory,accept=False);events.append({'operation':'submit contradictory fixed component without shrinking it',**failed})
        failed_spec=service.store.get(failed['revision_id'],'revision')['spec'];conflicts=analytic_conflicts(failed_spec)
        if failed['job_status']!='failed' or not conflicts:raise RuntimeError('Contradictory component was not exposed with a dimensional inequality')
        if service.project(pid)['active_revision_id']!=rid:raise RuntimeError('Failed candidate replaced accepted geometry')
        undone=service.history(pid,'undo');restored=undone['active_revision_id']
        events.append({'operation':'undo alternative-lid acceptance','active_revision':restored})
        service.close();service=Service(out/'state')
        reopened=service.project(pid)
        if reopened['active_revision_id']!=restored:raise RuntimeError('Restart lost accepted revision')
        export_dir=out/'exports';export_dir.mkdir(exist_ok=True)
        for filename in ('assembly.step','assembly.stl','assembly.svg','design.py','design.json','parameters.json','report.json','bundle.zip'):
            shutil.copy2(service.artifact(restored,filename,verify_all=True),export_dir/filename)
        independent=out/'independent-rebuild'
        rebuilt=subprocess.run([sys.executable,str(export_dir/'design.py'),'--output',str(independent)],cwd=export_dir,capture_output=True,text=True,timeout=120)
        if rebuilt.returncode:raise RuntimeError(f'Independent exported source failed: {rebuilt.stderr[-1500:]}')
        # A distinct process reopens the independent result and performs all contracts.
        original=service.store.get(restored,'revision');report=_verify_process(original['spec'],independent,out/'rebuild-verification')
        if report['status']!='PASS':raise RuntimeError('Independent source rebuilt geometry did not pass its contracts')
        before={p['id']:p for p in original['report']['parts']};after={p['id']:p for p in report['parts']}
        deltas={pid:{'volume_mm3':abs(before[pid]['volume']-after[pid]['volume']),'envelope_mm':[abs(a-b) for a,b in zip(before[pid]['bounds']['size'],after[pid]['bounds']['size'])]} for pid in before}
        if any(p['volume_mm3']>1e-5 or max(p['envelope_mm'])>1e-5 for p in deltas.values()):raise RuntimeError('Independent source changed measured geometry')
        events.append({'operation':'restart; export; rebuild source independently; remeasure','active_revision':restored,'status':report['status'],'deltas':deltas})
        family_results={}
        for family in ('plate','bracket'):
            new=service.new(f'Demo {family}',family);fid=new['project']['id'];first=_require_pass(_wait(service,new));frid=first['revision_id']
            dim=_require_pass(_wait(service,service.edit(fid,{'base_revision':frid,'parameters':{'width':110 if family=='plate' else 70}})));frid=dim['revision_id']
            # Layout changes are deliberate, explicitly reflected in the current pattern contract.
            layout=_require_pass(_wait(service,service.edit(fid,{'base_revision':frid,'parameters':{'mount_x':40 if family=='plate' else 24}})));frid=layout['revision_id']
            terminal='plate_edges' if family=='plate' else 'bracket_edges'
            extra=_slot(f'{family}_slot',family if family=='plate' else 'bracket',terminal,[8,3,10],[0,24,3] if family=='plate' else [0,10,3])
            slotted=_require_pass(_wait(service,service.edit(fid,{'base_revision':frid,'add_features':[extra]})))
            family_results[family]={'project_id':fid,'initial':first,'dimension_edit':dim,'layout_edit':layout,'slot_edit':slotted,'exports':str(service.store.root/'artifacts'/slotted['revision_id'])}
        result={'status':'PASS','project_id':pid,'active_revision':restored,'events':events,'comparison':comparison,'conflicts':conflicts,'families':family_results,'exports':str(export_dir),'independent_rebuild':str(independent),'duration_seconds':time.monotonic()-started,'tested_platform':platform.platform(),'machine':platform.machine(),'provider_integration':'unexercised: structured/manual workflow; no live model configured','manufacturing_validation':'software BREP checks only; no physical fit, FEA, print or certification trial'}
        return _write_report(out,'demo-results.json',result)
    finally:service.close()


def _verify_process(spec,artifacts,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    request=work/'verify-request.json';result=work/'verify-result.json'
    request.write_text(json.dumps({'spec':spec,'output_dir':str(artifacts),'limits':{'timeout_seconds':90,'output_mb':64,'memory_mb':2048}}))
    proc=subprocess.run([sys.executable,'-m','shapeloop.worker','verify',str(request),str(result)],capture_output=True,text=True,timeout=100)
    if proc.returncode or not result.exists():raise RuntimeError(f'Verification worker failed: {proc.stderr[-1000:]}')
    payload=json.loads(result.read_text())
    if not payload['ok']:raise RuntimeError(payload['error'])
    return payload['result']


def _build_and_measure(spec,artifacts,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    request=work/'build-request.json';result=work/'build-result.json'
    request.write_text(json.dumps({'spec':spec,'output_dir':str(artifacts),'limits':{'timeout_seconds':90,'output_mb':64,'memory_mb':2048}}))
    start=time.monotonic()
    proc=subprocess.run([sys.executable,'-m','shapeloop.worker','build',str(request),str(result)],capture_output=True,text=True,timeout=100)
    if proc.returncode or not result.exists():raise RuntimeError(f'Geometry worker failed: {proc.stderr[-1000:]}')
    payload=json.loads(result.read_text())
    if not payload['ok']:raise RuntimeError(payload['error'])
    report=_verify_process(spec,artifacts,work/'verification')
    return report,time.monotonic()-start


def _candidate(base,change):
    spec=copy.deepcopy(base)
    for key,value in change.get('parameters',{}).items():spec['parameters'][key]['value']=value
    for feature in change.get('add_features',[]):
        spec['features'].append(copy.deepcopy(feature))
        next(p for p in spec['parts'] if p['id']==feature['part'])['feature']=feature['id']
    return spec


def _metrics(report,desired,current,change,protected_constraints,accepted,seconds):
    indexed={m['id']:m for m in report['measurements']}
    preserved=sum(indexed[c]['status']=='PASS' for c in protected_constraints if c in indexed)
    requested=0;total=len(change.get('parameters',{}))+len(change.get('add_features',[]))
    for key,value in change.get('parameters',{}).items():requested+=current['parameters'][key]['value']==value
    ids={f['id'] for f in current['features']}
    requested+=sum(f['id'] in ids for f in change.get('add_features',[]))
    desired_norm=normalize(desired);current_norm=normalize(current)
    wanted={f['id']:f for f in desired_norm['features']};actual={f['id']:f for f in current_norm['features']}
    requested_names=set(change.get('parameters',{}))
    affected={f['id'] for f in change.get('add_features',[])}
    def references(value):
        if isinstance(value,str):
            import ast
            try:return {n.id for n in ast.walk(ast.parse(value,mode='eval')) if isinstance(n,ast.Name)}
            except SyntaxError:return set()
        if isinstance(value,dict):return set().union(*(references(v) for v in value.values())) if value else set()
        if isinstance(value,list):return set().union(*(references(v) for v in value)) if value else set()
        return set()
    for feature in desired['features']:
        if requested_names & references(feature['parameters']):affected.add(feature['id'])
    growing=True
    while growing:
        growing=False
        for feature in desired['features']:
            if feature['id'] not in affected and set(feature['inputs']) & affected:
                affected.add(feature['id']);growing=True
    unintended=sum(wanted.get(key)!=actual.get(key) for key in (set(wanted)|set(actual))-affected)
    return {'preserved_constraints':preserved,'required_preservation_constraints':len(protected_constraints),'requested_edits_achieved':requested,'requested_edits':total,'unintended_feature_changes':unintended,'repair_attempts':0,'candidate_check_failures':sum(m['status']!='PASS' and m['required'] for m in report['measurements']),'geometry_status':report['status'],'accepted':accepted,'wall_seconds':seconds}


def benchmark(output_dir,sequences=15):
    """Compare execution policies under identical deterministic intents, not model quality."""
    if not 1<=sequences<=100:raise ValueError('Choose 1 to100 generated sequences')
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True);started=time.monotonic();records=[]
    for sequence in range(sequences):
        family=('enclosure','plate','bracket')[sequence%3];variant=sequence//3
        base=recipe(family).model_dump(mode='json');base['parameters']['width']['value']+=variant*2
        # Freeze mounting requirements to the initial world datum coordinates: moving
        # these is now an intentional hard-contract conflict in the third operation.
        normalized=normalize(base)
        for c in base['constraints']:
            if c['type']=='hole_pattern':
                fixed=next(n for n in normalized['constraints'] if n['id']==c['id'])
                c['parameters']=copy.deepcopy(fixed['parameters'])
        terminal={'enclosure':'body_edges','plate':'plate_edges','bracket':'bracket_edges'}[family]
        part='body' if family=='enclosure' else family
        slot=_slot('bench_slot',part,terminal,[6,6,7],[0,-25,12]) if family=='enclosure' else _slot('bench_slot',part,terminal,[8,3,10],[0,24,3] if family=='plate' else [0,10,3])
        operations=[{'parameters':{'width':base['parameters']['width']['value']+4}}, {'add_features':[slot]}, {'parameters':{'mount_x':base['parameters']['mount_x']['value']+2}}]
        protected=[c['id'] for c in base['constraints'] if c['type']=='hole_pattern' and c.get('required',True)]
        for mode in ('full_regeneration','sequential_without_acceptance','shapeloop'):
            mode_dir=out/f'{sequence:02d}-{family}'/mode;mode_dir.mkdir(parents=True,exist_ok=True)
            current=copy.deepcopy(base);accumulated=[];service=None;project=None;rid=None
            if mode=='shapeloop':
                service=Service(mode_dir/'state');created=service.new(f'{family} comparison{sequence}',family,base);project=created['project']['id'];initial=_require_pass(_wait(service,created));rid=initial['revision_id']
            try:
                for step,change in enumerate(operations):
                    accumulated.append(change);desired=copy.deepcopy(base)
                    for past in accumulated:desired=_candidate(desired,past)
                    candidate=desired if mode=='full_regeneration' else _candidate(current,change)
                    if mode=='shapeloop':
                        then=time.monotonic();submitted=service.edit(project,{'base_revision':rid,**change});built=_wait(service,submitted,accept=True);seconds=time.monotonic()-then
                        report=built['report']
                        if report is None:raise RuntimeError(built['error'])
                        accepted=built['job_status']=='succeeded'
                        if accepted:rid=built['revision_id'];current=copy.deepcopy(candidate)
                        else:
                            # Metrics of accepted-state preservation use the actual accepted
                            # revision's earlier reopened-STEP report, while candidate failures
                            # remain separately visible below.
                            accepted_report=service.store.get(rid,'revision')['report']
                    else:
                        report,seconds=_build_and_measure(candidate,mode_dir/f'step{step}'/'artifacts',mode_dir/f'step{step}'/'workers');accepted=True;current=copy.deepcopy(candidate)
                    metric_report=accepted_report if mode=='shapeloop' and not accepted else report
                    metrics=_metrics(metric_report,desired,current,change,protected,accepted,seconds)
                    metrics['candidate_geometry_status']=report['status'];metrics['candidate_check_failures']=sum(m['status']!='PASS' and m['required'] for m in report['measurements'])
                    records.append({'sequence':sequence,'family':family,'mode':mode,'step':step,'operation':change,**metrics})
            finally:
                if service:service.close()
    totals={}
    for mode in ('full_regeneration','sequential_without_acceptance','shapeloop'):
        rows=[r for r in records if r['mode']==mode]
        totals[mode]={key:sum(r[key] for r in rows) for key in ('preserved_constraints','required_preservation_constraints','requested_edits_achieved','requested_edits','unintended_feature_changes','repair_attempts','candidate_check_failures','wall_seconds')}
        totals[mode]['failed_candidates']=sum(r['candidate_geometry_status']!='PASS' for r in rows)
        totals[mode]['accepted_invalid_candidates']=sum(r['accepted'] and r['candidate_geometry_status']!='PASS' for r in rows)
    result={'sequences':sequences,'operations_per_sequence':3,'records':records,'totals':totals,'duration_seconds':time.monotonic()-started,'comparison_scope':'Deterministic structured-intent execution policies, identical CadQuery kernel, generated families and operation budget. This does not evaluate language-model quality, usability, manufacturing outcomes or general product superiority.','baseline_definition':{'full_regeneration':'Recreate fresh recipe and apply all accumulated explicit structured intents on every operation; no acceptance gating.','sequential_without_acceptance':'Apply each intent to prior geometry specification and retain candidates regardless of diagnostic checks.','shapeloop':'Apply the same intents through durable jobs; measure exported STEP; accept only PASS; preserve the prior accepted revision on a deliberate mounting-contract conflict.'},'measurement_limits':'Baselines are measured after execution for comparison, but those measurements do not gate their state. Unintended changes count differences outside the requested parameter/feature dependency closure. Unachieved requested changes are counted separately. Changed parts rebuild their full DAG. ShapeLoop-CAD may reuse complete unchanged parts using a validated content-addressed BREP cache; every candidate still undergoes full STEP reimport checks. Actual wall times are reported without a general speed claim.','provider_integration':'unexercised: no configured live model; no model tokens or API monetary cost incurred','model_tokens':0,'network_requests':0,'tested_platform':platform.platform(),'machine':platform.machine()}
    return _write_report(out,'benchmark-results.json',result)

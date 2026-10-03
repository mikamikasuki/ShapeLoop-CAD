import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st
from shapeloop.api import create_app
from shapeloop.service import Service,StaleRevision
from shapeloop.spec import normalize
from shapeloop.recipes import recipe
from shapeloop.store import Store

@pytest.fixture()
def client(tmp_path):
    app=create_app(tmp_path/'state')
    with TestClient(app) as client:
        client.headers['X-ShapeLoop-Token']=client.get('/api/session').json()['token']
        yield client

def create(client,family='enclosure'):
    result=client.post('/api/projects',json={'name':'Test instrument','recipe':family}).json()
    assert 'job' in result,result
    job=client.app.state.service.jobs.wait(result['job']['id'])
    assert job['status']=='succeeded',job
    client.app.state.service.accept(result['revision']['id'])
    return result['project']['id'],result['revision']['id']

def candidate(client,project,base,parameters,**extra):
    response=client.post(f'/api/projects/{project}/edit',json={'base_revision':base,'parameters':parameters,**extra})
    assert response.status_code==200,response.text
    result=response.json(); job=client.app.state.service.jobs.wait(result['job']['id'])
    return result['revision']['id'],job

def test_api_live_edit_accept_fail_compare_undo_restart(client,tmp_path):
    pid,initial=create(client)
    edited,job=candidate(client,pid,initial,{'height':24})
    assert job['status']=='succeeded'
    report=client.get(f'/api/revisions/{edited}/measurements').json()
    hole=next(c for c in report['measurements'] if c['id']=='mounting_pattern')
    assert hole['status']=='PASS' and hole['actual']['count']==4
    assert client.post(f'/api/revisions/{edited}/accept').status_code==200
    failed,job=candidate(client,pid,edited,{'height':10})
    assert job['status']=='failed'
    assert client.post(f'/api/revisions/{failed}/accept').status_code==422
    project=client.get(f'/api/projects/{pid}').json()
    assert project['active_revision_id']==edited
    assert client.get(f'/api/artifacts/{edited}/assembly.step').status_code==200
    compare=client.get(f'/api/projects/{pid}/compare',params={'from':initial,'to':edited}).json()
    assert compare['parameters'][0]['parameter']=='height'
    assert 'body_blank' in compare['changed_features']
    assert client.post(f'/api/projects/{pid}/undo').json()['active_revision_id']==initial
    assert client.post(f'/api/projects/{pid}/redo').json()['active_revision_id']==edited
    # New Store reads completed state without depending on process memory.
    reopened=Store(client.app.state.service.store.root)
    assert reopened.get(pid,'project')['active_revision_id']==edited
    assert reopened.get(edited,'revision')['report']['status']=='PASS'

def test_csrf_origin_key_privacy_and_paths(client):
    token=client.headers.pop('X-ShapeLoop-Token')
    assert client.post('/api/projects',json={}).status_code==403
    client.headers['X-ShapeLoop-Token']=token
    assert client.post('/api/projects',json={},headers={'Origin':'https://example.com'}).status_code==403
    assert client.get('/api/session',headers={'Host':'public.example'}).status_code==403
    assert client.put('/api/settings',json={'provider':{'endpoint':'http://remote.example/v1'}}).status_code==422
    assert client.put('/api/settings',json={'provider':{'api_key':'private-test-secret'}}).status_code==200
    assert 'private-test-secret' not in client.get('/api/settings').text
    assert 'api_key' not in client.get('/api/settings').json()['provider']
    assert client.get('/api/artifacts/unknown/assembly.step').status_code==404

def test_stale_requests_dag_removal_and_protected_drift(client):
    pid,initial=create(client,'plate')
    edited,job=candidate(client,pid,initial,{'width':110})
    assert job['status']=='succeeded'
    assert client.post(f'/api/revisions/{edited}/accept').status_code==200
    assert client.post(f'/api/projects/{pid}/edit',json={'base_revision':initial,'parameters':{'width':120}}).status_code==409
    assert client.post(f'/api/projects/{pid}/edit',json={'base_revision':edited,'remove_features':['mount_holes']}).status_code==422
    service=client.app.state.service
    with pytest.raises(ValueError,match='implicitly alter'):
        service.edit(pid,{'base_revision':edited,'parameters':{'mount_x':39}},protected=True)
    with pytest.raises(ValueError,match='hard requirement'):
        service.edit(pid,{'base_revision':edited,'constraints':[]},protected=True)

def test_missing_provider_is_not_keyword_generation(client):
    assert client.post('/api/generate',json={'instruction':'制作一个机箱'}).status_code==503
    assert client.post('/api/provider/probe').status_code==503

def test_recover_interrupted_cancel_retry_and_timeout(tmp_path):
    service=Service(tmp_path/'state')
    service.settings.value['workers']['timeout_seconds']=1
    result=service.new('Timed primitive','plate')
    # Cancel an actual queued/running worker; preserve a retryable revision.
    service.jobs.cancel(result['job']['id'])
    job=service.jobs.wait(result['job']['id'])
    assert job['status']=='cancelled'
    service.settings.value['workers']['timeout_seconds']=120
    retried=service.jobs.submit(result['revision']['id'])
    assert service.jobs.wait(retried['id'])['status']=='succeeded'
    service.accept(result['revision']['id'])
    active=result['revision']['id']
    # A geometry worker with a real dense pattern is terminated by wall-clock cap.
    service.settings.value['workers']['timeout_seconds']=1
    spec=recipe('plate').model_dump(mode='json')
    spec['features'].append({'id':'many_bosses','name':'Dense bosses','type':'pattern','part':'plate','inputs':['plate_edges'],'parameters':{'profile':'cylinder','diameter':1,'height':8,'centers':[[x*2-40,y*2-20,0] for x in range(40) for y in range(10)]}})
    spec['parts'][0]['feature']='many_bosses'
    result=service.edit(result['project']['id'],{'base_revision':active,'spec':spec})
    timed=service.jobs.wait(result['job']['id'])
    assert timed['status']=='failed' and 'timeout' in timed['error'].lower()
    assert service.project(result['revision']['project_id'])['active_revision_id']==active
    # Simulate an interrupted persisted job, then construct a fresh service.
    record=service.store.insert('job',{'revision_id':result['revision']['id'],'status':'running'},result['revision']['project_id'])
    service.close()
    reopened=Service(tmp_path/'state')
    assert reopened.store.get(record['id'],'job')['status']=='interrupted'
    assert reopened.store.get(active,'revision')['report']['status']=='PASS'
    reopened.close()

def test_swapped_export_blocks_acceptance(client):
    pid,base=create(client,'plate')
    edited,job=candidate(client,pid,base,{'width':105})
    assert job['status']=='succeeded'
    service=client.app.state.service
    file=service.artifact(edited,'assembly.step')
    file.write_bytes(service.artifact(base,'assembly.step').read_bytes())
    response=client.post(f'/api/revisions/{edited}/accept')
    assert response.status_code==422 and 'integrity mismatch' in response.text
    assert service.project(pid)['active_revision_id']==base

def test_fresh_check_does_not_mutate_exports_and_bundle_tampering_fails(client):
    pid,base=create(client,'plate'); service=client.app.state.service
    before=service.artifact(base,'measurements.json').read_bytes()
    assert service.check(base)['status']=='PASS'
    assert service.artifact(base,'measurements.json').read_bytes()==before
    bundle=service.artifact(base,'bundle.zip')
    bundle.write_bytes(b'not the requested revision')
    assert client.get(f'/api/artifacts/{base}/bundle.zip').status_code==422

def test_remove_supported_leaf_and_brep_selection_measure(client):
    pid,base=create(client,'plate')
    response=client.post(f'/api/projects/{pid}/edit',json={'base_revision':base,'remove_features':['plate_edges']})
    assert response.status_code==200,response.text
    data=response.json(); service=client.app.state.service
    assert service.jobs.wait(data['job']['id'])['status']=='succeeded'
    mesh=client.get(f"/api/artifacts/{data['revision']['id']}/mesh.json").json()
    face=mesh['parts'][0]['faces'][0]['id']
    result=client.post(f"/api/revisions/{data['revision']['id']}/measure",json={'kind':'area','entities':[face]}).json()
    assert result['status']=='PASS' and result['actual']>0 and 'STEP' in result['method']
    result=client.post(f"/api/revisions/{data['revision']['id']}/measure",json={'kind':'distance','entities':[face,face]}).json()
    assert result['actual']==0 and result['unit']=='mm'
    result=client.post(f"/api/revisions/{data['revision']['id']}/measure",json={'entities':['plate:face:invalid']}).json()
    assert result['status']=='UNKNOWN'

def test_import_boundary_and_portable_step_source(client,tmp_path):
    pid,base=create(client,'plate')
    service=client.app.state.service
    spec=recipe('plate').model_dump(mode='json')
    spec['features'][0]['type']='import_step'; spec['features'][0]['parameters']={'path':str(service.artifact(base,'assembly.step'))}
    assert client.post('/api/projects',json={'spec':spec}).status_code==422
    source=service.artifact(base,'assembly.step').read_bytes()
    response=client.post('/api/imports',files={'file':('reference.step',source,'application/octet-stream')})
    assert response.status_code==200,response.text
    data=response.json()
    assert service.jobs.wait(data['job']['id'])['status']=='succeeded'
    export=service.artifact(data['revision']['id'],'design.py')
    import subprocess,sys,zipfile
    bundle=service.artifact(data['revision']['id'],'bundle.zip')
    portable=tmp_path/'portable'; portable.mkdir()
    with zipfile.ZipFile(bundle) as z:z.extractall(portable)
    rebuilt=subprocess.run([sys.executable,str(portable/'design.py'),'--output',str(tmp_path/'rebuilt')],cwd=tmp_path,capture_output=True,text=True,timeout=120)
    assert rebuilt.returncode==0,rebuilt.stderr
    assert (tmp_path/'rebuilt/assembly.step').stat().st_size>1000

@given(st.floats(min_value=60,max_value=160,allow_nan=False,allow_infinity=False))
def test_unit_conversion_keeps_physical_parameters(width):
    spec=recipe('plate').model_dump(mode='json'); spec['parameters']['width']['value']=width
    old=normalize(spec)
    Service._convert_units(spec,'in')
    new=normalize(spec)
    assert new['resolved_parameters']['width']==pytest.approx(old['resolved_parameters']['width'])
    assert new['features'][0]['parameters']['size']==pytest.approx(old['features'][0]['parameters']['size'])
    assert new['constraints'][0]['parameters']['size']==pytest.approx(old['constraints'][0]['parameters']['size'])

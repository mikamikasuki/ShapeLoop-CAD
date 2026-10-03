"""Real BREP checks and adversarial geometry fixtures, generated at runtime."""
import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest
import cadquery as cq
from shapeloop.spec import DesignSpec, Parameter, normalize
from shapeloop.recipes import recipe
from shapeloop.geometry import build
from shapeloop.compiler import compile_source
from shapeloop.verifier import verify


def run(spec,out):
    spec=spec.model_dump(mode='json') if isinstance(spec,DesignSpec) else spec
    build(spec,out)
    return verify(spec,out)

@pytest.mark.parametrize('family',['enclosure','plate','bracket'])
def test_real_recipe_contracts(family,tmp_path):
    result=run(recipe(family),tmp_path)
    assert result['status']=='PASS',result['measurements']
    mesh=json.loads((tmp_path/'mesh.json').read_text())
    assert all(p['positions'] and p['indices'] for p in mesh['parts'])
    assert any(f['feature_id'] for p in mesh['parts'] for f in p['faces'])
    assert cq.importers.importStep(str(tmp_path/'assembly.step')).val().isValid()
    assert (tmp_path/'assembly.svg').read_text().lstrip().startswith('<?xml') or '<svg' in (tmp_path/'assembly.svg').read_text()

@pytest.mark.parametrize('family',['enclosure','plate','bracket'])
@pytest.mark.parametrize('variant',range(5))
def test_fifteen_generated_edit_sequences(family,variant,tmp_path):
    """15 independent generated sequences, each with three successive edits."""
    spec=recipe(family)
    base=spec.parameters['width'].value
    edits=[('width',float(base)+variant*3+2),('hole_diameter',3+variant*.15),('height' if family!='plate' else 'thickness',24+variant if family=='enclosure' else 35+variant if family=='bracket' else 7+variant*.25)]
    mounting=copy.deepcopy(next(f.parameters['centers'] for f in spec.features if f.id=='mount_holes'))
    for index,(name,value) in enumerate(edits):
        spec.parameters[name].value=value
        result=run(spec,tmp_path/str(index))
        assert result['status']=='PASS',[(m['id'],m['status'],m['explanation']) for m in result['measurements'] if m['status']!='PASS']
        assert next(f.parameters['centers'] for f in spec.features if f.id=='mount_holes')==mounting


def test_wrong_hole_geometry_with_unchanged_labels_fails(tmp_path):
    spec=recipe('plate');run(spec,tmp_path)
    shape=cq.Workplane('XY').box(100,60,6,centered=(True,True,False)).val()
    for x,y in [(-38,-20),(39,-20),(38,20),(-38,20)]:
        shape=shape.cut(cq.Solid.makeCylinder(2.5,8,cq.Vector(x,y,-1)))
    cq.exporters.export(shape,str(tmp_path/'plate.step'))
    result=verify(spec.model_dump(mode='json'),tmp_path)
    hole=next(m for m in result['measurements'] if m['id']=='mounting_pattern')
    assert result['status']=='FAIL' and hole['status']=='FAIL'
    assert 'displacement_mm' in hole['explanation']


def test_deleted_required_hole_fails(tmp_path):
    spec=recipe('plate');run(spec,tmp_path)
    shape=cq.importers.importStep(str(tmp_path/'plate.step')).val()
    shape=shape.fuse(cq.Solid.makeCylinder(2.5,6,cq.Vector(38,20,0))).clean()
    cq.exporters.export(shape,str(tmp_path/'plate.step'))
    result=verify(spec.model_dump(mode='json'),tmp_path)
    hole=next(m for m in result['measurements'] if m['id']=='mounting_pattern')
    assert hole['status']=='FAIL' and hole['actual']['count']==3


def test_swapped_stale_export_fails(tmp_path):
    spec=recipe('plate');run(spec,tmp_path/'old')
    changed=recipe('plate');changed.parameters['width'].value=120;run(changed,tmp_path/'new')
    (tmp_path/'new'/'plate.step').write_bytes((tmp_path/'old'/'plate.step').read_bytes())
    result=verify(changed.model_dump(mode='json'),tmp_path/'new')
    assert result['status']=='FAIL'
    assert next(m for m in result['measurements'] if m['id']=='envelope')['status']=='FAIL'
    assert next(m for m in result['measurements'] if m['id']=='export_file:plate')['status']=='FAIL'


def test_forbidden_overlap_fails(tmp_path):
    raw=recipe('plate').model_dump(mode='json')
    raw['constraints'].append({'id':'keepout','name':'Forbidden component volume','type':'keepout','parameters':{'part':'plate','size':[10,10,4],'center':[0,0,2],'max_volume':.001}})
    result=run(raw,tmp_path)
    row=next(m for m in result['measurements'] if m['id']=='keepout')
    assert row['status']=='FAIL' and row['actual']>0


def test_valid_mesh_failing_brep_cannot_pass(tmp_path):
    raw=recipe('plate').model_dump(mode='json');run(raw,tmp_path)
    assert json.loads((tmp_path/'mesh.json').read_text())['parts'][0]['indices']
    (tmp_path/'plate.step').write_text('invalid STEP data')
    result=verify(raw,tmp_path)
    assert result['status']=='FAIL'
    assert next(m for m in result['measurements'] if m['id']=='brep:plate')['status']=='FAIL'


def test_unsupported_mandatory_check_is_unknown(tmp_path):
    raw=recipe('plate').model_dump(mode='json');raw['constraints'].append({'id':'unsupported','name':'Global wall thickness','type':'global_minimum_wall','parameters':{}})
    result=run(raw,tmp_path)
    assert result['status']=='UNKNOWN'


def test_dimensions_cycles_missing_references_and_injection():
    spec=recipe('plate');spec.parameters['angle']=Parameter(value=2,dimension='angle')
    spec.parameters['width'].value='depth+angle'
    with pytest.raises(ValueError,match='Cannot add'):normalize(spec)
    raw=recipe('plate').model_dump(mode='json');raw['features'][0]['inputs']=['plate_edges']
    with pytest.raises(ValueError,match='cycle'):DesignSpec.model_validate(raw)
    raw=recipe('plate').model_dump(mode='json');raw['features']=[f for f in raw['features'] if f['id']!='mount_holes']
    with pytest.raises(ValueError,match='missing feature'):DesignSpec.model_validate(raw)
    spec=recipe('plate');spec.parameters['width'].value="__import__('os').system('whoami')"
    with pytest.raises(ValueError,match='Only names'):normalize(spec)


def test_inch_inputs_normalize_to_mm_and_reimport(tmp_path):
    raw={'name':'Inch block','units':'in','parameters':{'width':{'value':2,'dimension':'length'}},'parts':[{'id':'block','name':'Block','feature':'blank'}],'features':[{'id':'blank','name':'Blank','part':'block','type':'box','parameters':{'size':['width',1,.5],'center':[0,0,.25]}}],'constraints':[{'id':'bounds','name':'Bounds','type':'envelope','parameters':{'size':['width',1,.5]}}]}
    result=run(raw,tmp_path)
    assert result['status']=='PASS'
    bounds=result['parts'][0]['bounds']['size']
    assert bounds==pytest.approx([50.8,25.4,12.7],abs=1e-6)


def test_semantic_refs_after_topology_change_and_transform(tmp_path):
    spec=recipe('plate');spec.parameters['edge_chamfer'].value=1
    spec.parts[0].transform.translation=[5,7,2]
    # Envelope center is unconstrained; the mounting pattern is explicitly world-based.
    raw=spec.model_dump(mode='json')
    hole=next(c for c in raw['constraints'] if c['id']=='mounting_pattern')
    hole['parameters']['centers']=[['-mount_x+5*mm','-mount_y+7*mm',0],['mount_x+5*mm','-mount_y+7*mm',0],['mount_x+5*mm','mount_y+7*mm',0],['-mount_x+5*mm','mount_y+7*mm',0]]
    floor=next(c for c in raw['constraints'] if c['id']=='plate_floor');floor['parameters']['start']=[5,7,1]
    result=run(raw,tmp_path)
    assert result['status']=='PASS'
    mesh=json.loads((tmp_path/'mesh.json').read_text())
    assert any(f['feature_id']=='mount_holes' for f in mesh['parts'][0]['faces'])


def test_self_contained_source_rebuild(tmp_path):
    spec=recipe('plate');source=tmp_path/'design.py';source.write_text(compile_source(spec))
    assert 'from shapeloop' not in source.read_text()
    proc=subprocess.run([sys.executable,str(source),'--parameters','{"width":110}','--output',str(tmp_path/'rebuilt')],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stderr
    changed=recipe('plate');changed.parameters['width'].value=110
    result=verify(changed.model_dump(mode='json'),tmp_path/'rebuilt')
    assert result['status']=='PASS'


def test_composable_sketch_boolean_slot_and_pattern(tmp_path):
    raw={'name':'Custom supported graph','parameters':{},'parts':[{'id':'custom','name':'Custom','feature':'moved'}],'features':[
        {'id':'sketch','name':'Rectangle sketch','part':'custom','type':'extrude','parameters':{'profile':'rectangle','width':40,'height':20,'depth':5}},
        {'id':'add','name':'Addition','part':'custom','type':'pattern','inputs':['sketch'],'parameters':{'profile':'cylinder','diameter':5,'height':8,'centers':[[-10,0,0],[10,0,0]],'z':0}},
        {'id':'slot','name':'Rectangular slot','part':'custom','type':'slot','inputs':['add'],'parameters':{'size':[4,10,10],'center':[0,0,5]}},
        {'id':'tool','name':'Boolean tool','part':'custom','type':'box','parameters':{'size':[10,30,20],'center':[20,0,5]}},
        {'id':'cut','name':'Boolean cut','part':'custom','type':'subtract','inputs':['slot','tool'],'parameters':{}},
        {'id':'moved','name':'Explicit transform','part':'custom','type':'transform','inputs':['cut'],'parameters':{'translation':[1,2,3],'rotation':[0,0,0]}},
    ],'constraints':[{'id':'valid','name':'Valid solid','type':'brep','parameters':{'part':'custom','expected_solids':1}}]}
    assert run(raw,tmp_path)['status']=='PASS'


def test_impossible_fillet_reports_kernel_failure(tmp_path):
    spec=recipe('enclosure');spec.parameters['fillet_radius'].value=100
    with pytest.raises(Exception):build(spec.model_dump(mode='json'),tmp_path)


def test_safe_part_cache_reuse_invalidation_and_corruption(tmp_path):
    spec=recipe('enclosure');cache=tmp_path/'cache'
    first=build(spec.model_dump(mode='json'),tmp_path/'first',cache_dir=cache)
    assert first['cache_reused_parts']==[]
    second=build(spec.model_dump(mode='json'),tmp_path/'second',cache_dir=cache)
    assert second['cache_reused_parts']==['body','lid']
    assert verify(spec.model_dump(mode='json'),tmp_path/'second')['status']=='PASS'
    spec.parameters['fillet_radius'].value=1
    changed=build(spec.model_dump(mode='json'),tmp_path/'changed',cache_dir=cache)
    assert changed['cache_reused_parts']==['lid']
    assert verify(spec.model_dump(mode='json'),tmp_path/'changed')['status']=='PASS'
    # Break every BREP payload while retaining plausible JSON mesh/manifests.
    for entry in cache.iterdir():
        if entry.is_dir():(entry/'shape.brep').write_text('invalid BREP')
    rebuilt=build(spec.model_dump(mode='json'),tmp_path/'rebuilt',cache_dir=cache)
    assert rebuilt['cache_reused_parts']==[]
    assert verify(spec.model_dump(mode='json'),tmp_path/'rebuilt')['status']=='PASS'


def test_part_cache_transform_and_semantic_mapping(tmp_path):
    spec=recipe('plate');cache=tmp_path/'cache'
    build(spec.model_dump(mode='json'),tmp_path/'first',cache_dir=cache)
    reused=build(spec.model_dump(mode='json'),tmp_path/'reused',cache_dir=cache)
    assert reused['cache_reused_parts']==['plate']
    mesh=json.loads((tmp_path/'reused'/'mesh.json').read_text())
    assert any(f['feature_id']=='mount_holes' for f in mesh['parts'][0]['faces'])
    spec.parts[0].transform.translation=[5.,0.,0.]
    transformed=build(spec.model_dump(mode='json'),tmp_path/'transformed',cache_dir=cache)
    assert transformed['cache_reused_parts']==[]
    assert transformed['parts'][0]['bounds']['center'][0]==pytest.approx(5)


def test_portable_imported_step_source_rebuild(tmp_path):
    bundle=tmp_path/'bundle';bundle.mkdir()
    cq.exporters.export(cq.Workplane('XY').box(12,8,4).val(),str(bundle/'reference.step'))
    raw={'name':'Portable direct STEP','family':'imported','parts':[{'id':'direct','name':'Direct STEP part','feature':'import'}],'features':[{'id':'import','name':'Imported geometry','type':'import_step','part':'direct','parameters':{'path':'reference.step'}}],'constraints':[{'id':'envelope','name':'Envelope','type':'envelope','parameters':{'size':[12,8,4]}}]}
    source=bundle/'design.py';source.write_text(compile_source(raw))
    unrelated=tmp_path/'other-working-directory';unrelated.mkdir()
    proc=subprocess.run([sys.executable,str(source),'--output',str(tmp_path/'rebuilt')],cwd=unrelated,capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stderr
    moved_spec=copy.deepcopy(raw);moved_spec['features'][0]['parameters']['path']=str(bundle/'reference.step')
    result=verify(moved_spec,tmp_path/'rebuilt')
    assert result['status']=='PASS'


def test_fractional_counts_nonfinite_and_negative_tolerances_rejected():
    raw=recipe('plate').model_dump(mode='json')
    raw['constraints'][1]['parameters']['count']=4.5
    with pytest.raises(ValueError,match='positive integer'):normalize(raw)
    raw=recipe('plate').model_dump(mode='json');raw['features'][0]['parameters']['size'][0]=float('inf')
    with pytest.raises(ValueError,match='finite'):normalize(raw)
    raw=recipe('plate').model_dump(mode='json');raw['constraints'][0]['tolerance']=-1
    with pytest.raises(ValueError):DesignSpec.model_validate(raw)


def test_named_translated_cm_datum_measured_from_step(tmp_path):
    raw={'name':'Datum unit check','units':'cm','parameters':{'offset':{'value':3,'dimension':'length'}},'datums':{'shift':{'origin':['offset',1,2],'axes':'XYZ'}},'parts':[{'id':'block','name':'Block','feature':'blank','transform':{'translation':['offset',1,2]}}],'features':[{'id':'blank','name':'Blank','part':'block','type':'box','parameters':{'size':[2,1,.5],'center':[0,0,0]}}],'constraints':[{'id':'frame_bounds','name':'Bounds in shift datum','type':'envelope','parameters':{'size':[2,1,.5],'center':[0,0,0],'frame':'shift'},'tolerance':.001}]}
    normalized=normalize(raw)
    assert normalized['datums']['shift']['origin']==[30,10,20]
    result=run(raw,tmp_path)
    assert result['status']=='PASS'
    row=next(m for m in result['measurements'] if m['id']=='frame_bounds')
    assert row['actual']['center']==pytest.approx([0,0,0],abs=1e-6)
    assert row['tolerances']['length_mm']==.01

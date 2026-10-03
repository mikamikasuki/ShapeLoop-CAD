"""Independent acceptance pass over exported STEP geometry, never display meshes."""
from __future__ import annotations
from pathlib import Path
import json
import math
import hashlib
from .spec import normalize
from .geometry import _bbox, _box, _runtime_fingerprint


LINEAR_TOLERANCE_MM = 0.01
ANGULAR_TOLERANCE_RAD = 1e-7
VOLUME_TOLERANCE_MM3 = 0.001
NUMBER_TOLERANCE = 1e-9


def _cylinders(shape):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    cylinders=[]
    for face in shape.Faces():
        if face.geomType()!='CYLINDER':continue
        cylinder=BRepAdaptor_Surface(face.wrapped).Cylinder()
        axis=cylinder.Axis(); location=axis.Location();direction=axis.Direction()
        d=[direction.X(),direction.Y(),direction.Z()];c=[location.X(),location.Y(),location.Z()]
        # Canonicalize axes' direction and axial coordinate. A cylinder's origin
        # slides along its own axis during export, so it is not a persistent center.
        if next((x for x in d if abs(x)>1e-8),1)<0:d=[-x for x in d]
        dot=sum(x*y for x,y in zip(c,d));center=[x-dot*y for x,y in zip(c,d)]
        u=(BRepAdaptor_Surface(face.wrapped).FirstUParameter()+BRepAdaptor_Surface(face.wrapped).LastUParameter())/2
        v=(BRepAdaptor_Surface(face.wrapped).FirstVParameter()+BRepAdaptor_Surface(face.wrapped).LastVParameter())/2
        normal,surface_point=face.normalAt(u,v)
        radial=[surface_point.toTuple()[i]-center[i] for i in range(3)]
        axial=sum(radial[i]*d[i] for i in range(3));radial=[radial[i]-axial*d[i] for i in range(3)]
        inward=sum(normal.toTuple()[i]*radial[i] for i in range(3))<0
        record={"inward":inward,"diameter":2*cylinder.Radius(),"axis":d,"center":center,"bounds":_bbox(face),"face":face}
        if not any(abs(a['diameter']-record['diameter'])<1e-5 and math.dist(a['center'],center)<1e-5 and math.dist(a['axis'],d)<1e-5 for a in cylinders):cylinders.append(record)
    return cylinders


def _measurement(id, name, status, actual, expected=None, unit='', tolerance=.01, features=(), method='', explanation='', required=True):
    return {"id":id,"name":name,"status":status,"actual":actual,"expected":expected,"unit":unit,"tolerance":tolerance,"features":list(features),"method":method,"explanation":explanation,"required":required}


def _transformed(shape,frame,runtime):
    from .geometry import _transform
    if frame in ('origin',None):return shape
    datum=runtime.get('datums',{}).get(frame)
    if not datum:raise ValueError(f"Unknown measurement frame {frame}")
    # Initial exact support: translated coordinate frames with XYZ axes.
    if datum.get('axes','XYZ')!='XYZ' or datum.get('rotation',[0,0,0])!=[0,0,0]:
        raise NotImplementedError('Envelope measurement supports translated XYZ datum frames only')
    return shape.translate(tuple(-float(v) for v in datum.get('origin',[0,0,0])))


def verify(spec_dict, output_dir):
    import cadquery as cq
    runtime=normalize(spec_dict);out=Path(output_dir);measurements=[];parts={};summaries=[]
    try:metadata=json.loads((out/'metadata.json').read_text())
    except Exception as exc:
        metadata={};measurements.append(_measurement('export_manifest','Export manifest','UNKNOWN',None,method='filesystem',explanation=str(exc)))
    digest=_runtime_fingerprint(runtime)
    measurements.append(_measurement('revision_binding','STEP revision binding','PASS' if metadata.get('spec_sha256')==digest else 'FAIL',metadata.get('spec_sha256'),digest,method='normalized DesignSpec digest',explanation='Manifest must belong to the current specification; geometry checks below independently inspect its STEP.'))
    for part in runtime['parts']:
        pid=part['id'];path=out/f'{pid}.step';md=next((p for p in metadata.get('parts',[]) if p['id']==pid),{})
        try:
            shape=cq.importers.importStep(str(path)).val();valid=shape.isValid();solids=len(shape.Solids());volume=shape.Volume()
            ok=valid and solids>0 and volume>1e-9
            measurements.append(_measurement(f'brep:{pid}',f'{part["name"]} BREP','PASS' if ok else 'FAIL',{'valid':valid,'solids':solids,'volume':volume},unit='mm³',method='STEP reimport / OCCT BREP validity and mass properties'))
            parts[pid]=shape;summaries.append({'id':pid,'name':part['name'],'bounds':_bbox(shape),'volume':volume,'solids':solids,'valid':valid})
            actual_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            measurements.append(_measurement(f'export_file:{pid}',f'{part["name"]} export identity','PASS' if actual_hash==md.get('sha256') else 'FAIL',actual_hash,md.get('sha256'),method='export file digest',explanation='Detects changed, swapped, or stale part exports.'))
            measurements.append(_measurement(f'export_volume:{pid}',f'{part["name"]} export/reimport volume','PASS' if abs(volume-md.get('volume',float('inf')))<max(1e-5,volume*1e-7) else 'FAIL',volume,md.get('volume'),unit='mm³',tolerance=max(1e-5,volume*1e-7),method='Reimported STEP volume against original BREP mass property'))
        except Exception as exc:
            measurements.append(_measurement(f'brep:{pid}',f'{part["name"]} BREP','FAIL',None,method='STEP reimport',explanation=f'{type(exc).__name__}: {exc}'))
    if len(parts)==len(runtime['parts']):
        try:
            combined=cq.Compound.makeCompound(list(parts.values()));assembly=cq.importers.importStep(str(out/'assembly.step')).val();volume=sum(s.Volume() for s in parts.values())
            gap=max(abs(a-b) for a,b in zip(_bbox(combined)['size'],_bbox(assembly)['size']))
            vol_delta=abs(assembly.Volume()-volume);solid_ok=len(assembly.Solids())==sum(len(s.Solids()) for s in parts.values())
            ok=assembly.isValid() and solid_ok and gap<.01 and vol_delta<max(1e-5,volume*1e-7)
            measurements.append(_measurement('assembly_export','Assembly export/reimport','PASS' if ok else 'FAIL',{'envelope_delta':gap,'volume_delta':vol_delta,'solids':len(assembly.Solids())},unit='mm / mm³',method='Reopen assembly STEP; compare actual part union envelope, solid count and mass properties'))
        except Exception as exc:measurements.append(_measurement('assembly_export','Assembly export/reimport','FAIL',None,method='assembly STEP reimport',explanation=str(exc)))
    for constraint in runtime['constraints']:
        cid=constraint['id'];kind=constraint['type'];p=constraint['parameters'];tol=constraint['tolerance'];status='UNKNOWN';actual=None;expected=None;unit='mm';method='';explanation=''
        try:
            if kind=='envelope':
                ids=p.get('parts',list(parts));shape=cq.Compound.makeCompound([parts[pid] for pid in ids]);shape=_transformed(shape,p.get('frame','origin'),runtime);actual=_bbox(shape);expected=p.get('size',p.get('max_size'));method='Exact OCCT bounding box of reimported STEP in specified datum frame'
                if 'max_size' in p:status='PASS' if all(a<=b+tol for a,b in zip(actual['size'],p['max_size'])) else 'FAIL'
                else:status='PASS' if all(abs(a-b)<=tol for a,b in zip(actual['size'],expected)) else 'FAIL'
                if 'center' in p and math.dist(actual['center'],p['center'])>tol:status='FAIL';explanation='Envelope center moved relative to the datum.'
            elif kind in ('hole_pattern','hole'):
                shape=parts[p['part']];axis=p.get('axis','Z');direction={'X':[1,0,0],'Y':[0,1,0],'Z':[0,0,1]}[axis];axis_i={'X':0,'Y':1,'Z':2}[axis]
                target=p.get('centers',[p.get('center',[0,0,0])]);expected={'diameter':p['diameter'],'centers':target,'axis':axis,'count':int(p.get('count',len(target)))}
                angular_tol=math.radians(p['angular_tolerance']) if 'angular_tolerance' in p else ANGULAR_TOLERANCE_RAD
                candidates=[c for c in _cylinders(shape) if c['inward'] and abs(c['diameter']-p['diameter'])<=tol and math.dist(c['axis'],direction)<angular_tol]
                # Cylindrical faces can be bosses. A supported through-hole must be a
                # void at its axis throughout this part's bounding interval.
                bbox=_bbox(shape);voids=[]
                for c in candidates:
                    beginning=list(c['center']);ending=list(c['center'])
                    beginning[axis_i]=bbox['min'][axis_i]-tol;ending[axis_i]=bbox['max'][axis_i]+tol
                    probe=cq.Edge.makeLine(cq.Vector(*beginning),cq.Vector(*ending))
                    # Exact Boolean line/material common detects a blind floor even
                    # when a few sample points would miss it.
                    occupied=shape.intersect(probe)
                    if not occupied.Edges():voids.append(c)
                actual={'diameters':[c['diameter'] for c in voids],'centers':[c['center'] for c in voids],'axis':axis,'count':len(voids),'center_spacing':[math.dist(voids[i]['center'],voids[j]['center']) for i in range(len(voids)) for j in range(i+1,len(voids))]}
                unmatched=list(voids);errors=[]
                for center in target:
                    expected_center=list(center);expected_center[axis_i]=0
                    nearest=min(unmatched,key=lambda c:math.dist(c['center'],expected_center),default=None)
                    if nearest is None:errors.append({'expected_center':expected_center,'error':'required hole missing'})
                    elif math.dist(nearest['center'],expected_center)>tol:errors.append({'expected_center':expected_center,'actual_center':nearest['center'],'displacement_mm':math.dist(nearest['center'],expected_center)})
                    if nearest in unmatched:unmatched.remove(nearest)
                status='PASS' if not errors and len(voids)==expected['count'] else 'FAIL';method='Analytic inward cylindrical surfaces and exact line/BREP axis-void classification of reopened STEP; datum-relative axis coordinates'
                if errors:explanation=json.dumps(errors)
                elif status=='FAIL':explanation=f"Expected {expected['count']} holes of diameter {p['diameter']} mm; found {len(voids)}."
            elif kind=='thickness':
                shape=parts[p['part']];direction=p.get('direction',[0,0,1]);length=math.sqrt(sum(x*x for x in direction))
                if not length or sum(abs(x)>1e-8 for x in direction)!=1:raise NotImplementedError('Exact thickness probes support one coordinate axis')
                end=[a+b/length*p['length'] for a,b in zip(p['start'],direction)]
                edge=cq.Edge.makeLine(cq.Vector(*p['start']),cq.Vector(*end));common=shape.intersect(edge);segments=common.Edges()
                actual={'thickness':sum(e.Length() for e in segments),'segments':len(segments),'start':p['start'],'end':end};expected=p['expected'];method='Exact line/BREP Boolean common in named supported planar region'
                if len(segments)!=1:status='UNKNOWN';explanation='Probe intersects zero or multiple material intervals; a unique planar wall is not identified.'
                else:status='PASS' if abs(actual['thickness']-expected)<=tol else 'FAIL'
            elif kind=='keepout':
                selected=p.get('parts',[p['part']]);shape=cq.Compound.makeCompound([parts[pid] for pid in selected]);box=_box(p['size'],p['center']);overlap=shape.intersect(box).Volume();expected=p.get('max_volume',VOLUME_TOLERANCE_MM3);unit='mm³';method='Actual Boolean common volume against named box keep-out';status='PASS' if overlap<=expected else 'FAIL'
                actual=overlap
                if p.get('inside_envelope',False):
                    bounds=_bbox(shape);component=_bbox(box)
                    length_tol=p.get('linear_tolerance',LINEAR_TOLERANCE_MM)
                    contained=all(component['min'][i]>=bounds['min'][i]-length_tol and component['max'][i]<=bounds['max'][i]+length_tol for i in range(3))
                    actual={'overlap_volume':overlap,'contained_in_assembly_envelope':contained,'component_bounds':component,'assembly_bounds':bounds}
                    method+='; exact component-versus-assembly BREP bounds containment'
                    if not contained:
                        status='FAIL';explanation='Fixed component extends beyond the measured assembly envelope. Its dimensions and datum position remain unchanged.'
                if overlap>expected:explanation=f'Named keep-out overlaps {selected} by {overlap:.6g} mm³.'
            elif kind=='clearance':
                first=parts[p['parts'][0]];second=parts[p['parts'][1]] if len(p.get('parts',[]))>1 else _box(p['size'],p['center']);actual=first.distance(second);expected=p['minimum'];method='OCCT minimum BREP distance';status='PASS' if actual+tol>=expected else 'FAIL'
            elif kind=='interference':
                first,second=[parts[pid] for pid in p['parts']];overlap=first.intersect(second).Volume();distance=first.distance(second);volume_tol=p.get('volume_tolerance',VOLUME_TOLERANCE_MM3);actual={'overlap_volume':overlap,'distance':distance};expected={'max_overlap_volume':volume_tol,'contact_allowed':p.get('allowed_contact',False)};unit='mm³ / mm';method='Actual Boolean common volume and OCCT distance of assembly-position STEP solids'
                status='PASS' if overlap<=volume_tol and (p.get('allowed_contact',False) or distance>tol) else 'FAIL'
                if overlap>volume_tol:explanation=f'Parts {p["parts"]} interfere by {overlap:.6g} mm³.'
                elif status=='FAIL':explanation='Undeclared part contact: zero separation requires allowed_contact=true.'
            elif kind=='internal_clearance':
                # Supported contract identifies a fixed datum box to contain a component;
                # the component is never shrunk to resolve contradictory dimensions.
                shape=parts[p['part']];component=_box(p['size'],p['center']);actual={'overlap_volume':shape.intersect(component).Volume(),'clearance':shape.distance(component)};expected={'minimum':p.get('minimum',0),'max_overlap_volume':p.get('max_volume',VOLUME_TOLERANCE_MM3)};method='Boolean occupied-material overlap and BREP distance from fixed component box';status='PASS' if actual['overlap_volume']<=expected['max_overlap_volume'] and actual['clearance']+tol>=expected['minimum'] else 'FAIL'
                if status=='FAIL':explanation=f'Fixed internal component overlaps material by {actual["overlap_volume"]:.6g} mm³ or lacks its requested clearance.'
            elif kind=='brep':
                shape=parts[p['part']];actual={'valid':shape.isValid(),'solids':len(shape.Solids())};expected={'solids':int(p.get('expected_solids',1))};method='OCCT BREP validity';status='PASS' if actual['valid'] and actual['solids']==expected['solids'] else 'FAIL';unit='count'
            else:explanation=f'Unsupported measurement {kind}; mandatory unknowns prevent acceptance.'
        except (KeyError,NotImplementedError) as exc:explanation=f'Unresolved or unsupported reference: {exc}'
        except Exception as exc:explanation=f'Kernel measurement failed: {type(exc).__name__}: {exc}'
        measurement=_measurement(cid,constraint['name'],status,actual,expected,unit,p.get('max_volume',VOLUME_TOLERANCE_MM3) if kind=='keepout' else NUMBER_TOLERANCE if kind=='brep' else tol,constraint.get('features',[]),method,explanation,constraint['required'])
        measurement['tolerances']={'length_mm':p.get('linear_tolerance',LINEAR_TOLERANCE_MM) if kind=='keepout' else tol,'angular_rad':math.radians(p['angular_tolerance']) if 'angular_tolerance' in p else ANGULAR_TOLERANCE_RAD,'volume_mm3':p.get('volume_tolerance',p.get('max_volume',VOLUME_TOLERANCE_MM3)),'number':p.get('number_tolerance',NUMBER_TOLERANCE)}
        measurements.append(measurement)
    required=[m for m in measurements if m['required']]
    status='FAIL' if any(m['status']=='FAIL' for m in required) else 'UNKNOWN' if any(m['status']=='UNKNOWN' for m in required) else 'PASS'
    result={'status':status,'passed':status=='PASS','units':'mm','measurements':measurements,'parts':summaries,'limitations':['Generator and verifier use the same CadQuery/OCCT kernel; this is dimensional software validation, not independent physical validation.','Exact thickness is limited to the named axis-aligned line probe; no global minimum wall thickness guarantee.','Hole contracts cover axis-aligned through-holes, not arbitrary blind, threaded, counterbored or oblique holes.']}
    (out/'measurements.json').write_text(json.dumps(result,indent=2))
    return result


def analytic_conflicts(spec_dict):
    """Proof only for the rectangular enclosure recipe, never nonlinear search failure."""
    runtime=normalize(spec_dict)
    if runtime.get('family')!='enclosure':return []
    values=runtime['resolved_parameters']
    if not all(key in values for key in ('width','depth','height','wall','lid_thickness')):return []
    nodes={f['id']:f for f in runtime['features']}
    blank,cavity,lid=[nodes.get(key,{}) for key in ('body_blank','body_cavity','lid_blank')]
    if blank.get('type')!='box' or cavity.get('type')!='pocket' or lid.get('type')!='box':return []
    if cavity.get('inputs')!=['body_blank']:return []
    expected_blank=[values['width'],values['depth'],values['height']-values['lid_thickness']]
    expected_cavity=[values['width']-2*values['wall'],values['depth']-2*values['wall'],values['height']]
    expected_lid=[values['width'],values['depth'],values['lid_thickness']]
    if any(len(feature.get('parameters',{}).get('size',[]))!=3 or any(abs(a-b)>1e-8 for a,b in zip(feature['parameters']['size'],expected)) for feature,expected in ((blank,expected_blank),(cavity,expected_cavity),(lid,expected_lid))):return []
    if any(any(abs(a-b)>1e-8 for a,b in zip(part.get('transform',{}).get('translation',[0,0,0])+part.get('transform',{}).get('rotation',[0,0,0]),[0]*6)) for part in runtime['parts']):return []
    canonical_ids={'body_blank','body_cavity','bosses','mount_holes','body_edges','lid_blank','lid_holes'}
    extra=[f for f in runtime['features'] if f['id'] not in canonical_ids]
    if any(f['type'] not in ('hole','pocket','slot','fillet','chamfer') for f in extra):return []
    # Later cutouts can remove a wall locally. The wall/cavity formula is only
    # proven for the intact recipe; otherwise use the weaker necessary bound of
    # containing a fixed component within the unchanged outer envelope.
    intact=not extra
    conflicts=[]
    for c in runtime['constraints']:
        if not c['required'] or c['type'] not in ('keepout','internal_clearance'):continue
        p=c['parameters']
        if p.get('part')!='body' or 'size' not in p or 'center' not in p:continue
        gap=p.get('minimum',0)
        for i,axis in enumerate(('width','depth','height')):
            if not intact:
                required=p['size'][i]+2*gap
                inequality=f"{axis} ≥ component_{axis} + 2 × clearance = {required:g} mm"
            elif i<2:
                required=p['size'][i]+2*values['wall']+2*gap
                inequality=f"{axis} ≥ component_{axis} + 2 × wall + 2 × clearance = {required:g} mm"
            else:
                required=p['size'][i]+values['wall']+values['lid_thickness']+2*gap
                inequality=f"height ≥ component_height + base + lid + 2 × clearance = {required:g} mm"
            if values[axis]+c['tolerance']<required:
                conflicts.append({'constraints':[c['id'],'envelope'],'type':'analytical_dimension_conflict','axis':axis,'actual':values[axis],'minimum':required,'unit':'mm','inequality':inequality,'explanation':f"Fixed internal component cannot fit the requested {axis} envelope. Component dimensions remain unchanged.",'choices':[f'Increase {axis} to at least {required:g} mm','Explicitly revise the component requirement or clearance']})
        bottom=p['center'][2]-p['size'][2]/2-gap
        top=p['center'][2]+p['size'][2]/2+gap
        lower=values['wall'] if intact else 0
        upper=values['height']-values['lid_thickness'] if intact else values['height']
        if bottom<lower-c['tolerance'] or top>upper+c['tolerance']:
            conflicts.append({'constraints':[c['id'],'envelope'],'type':'datum_position_conflict','actual':{'component_bottom':bottom,'component_top':top},'expected':{'minimum_bottom':lower,'maximum_top':upper},'unit':'mm','inequality':f"allowed_bottom {lower:g} ≤ component_bottom {bottom:g} and component_top {top:g} ≤ allowed_top {upper:g}",'explanation':'Fixed datum-relative component position intersects the base or closed lid envelope.','choices':['Increase the envelope','Explicitly revise component position or dimensions']})
    return conflicts

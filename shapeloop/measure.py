"""Revision-local selection measurements on the actual reopened BREP."""
from __future__ import annotations
import json
import math
from pathlib import Path

def measure(output_dir,entities,kind='distance'):
    import cadquery as cq
    out=Path(output_dir)
    mesh=json.loads((out/'mesh.json').read_text())
    resolved=[]
    for entity in entities:
        part=next((p for p in mesh['parts'] if any(f['id']==entity for f in p['faces'])),None)
        if part is None: return {'status':'UNKNOWN','explanation':f'Selection {entity} does not belong to this revision'}
        record=next(f for f in part['faces'] if f['id']==entity)
        shape=cq.importers.importStep(str(out/f"{part['id']}.step")).val()
        candidates=[f for f in shape.Faces() if f.geomType()==record['geometry_type'] and math.dist(f.Center().toTuple(),record['center'])<1e-4 and abs(f.Area()-record['area'])<max(1e-4,record['area']*1e-7)]
        if len(candidates)!=1: return {'status':'UNKNOWN','explanation':f'Reference {entity} resolves to {len(candidates)} faces; clarify the selection'}
        resolved.append(candidates[0])
    if kind=='distance' and len(resolved)==2:
        return {'status':'PASS','actual':resolved[0].distance(resolved[1]),'unit':'mm','entities':entities,'method':'OCCT minimum distance between uniquely resolved reopened STEP faces','tolerance':.01}
    if kind=='area' and len(resolved)==1:
        return {'status':'PASS','actual':resolved[0].Area(),'unit':'mm²','entities':entities,'method':'OCCT surface mass properties of uniquely resolved reopened STEP face','tolerance':.0001}
    if kind=='angle' and len(resolved)==2 and all(f.geomType()=='PLANE' for f in resolved):
        a,b=[f.normalAt().normalized() for f in resolved]
        angle=math.degrees(math.acos(max(-1,min(1,a.dot(b)))))
        return {'status':'PASS','actual':angle,'unit':'deg','entities':entities,'method':'Angle between normals of uniquely resolved planar STEP faces','tolerance':.01}
    return {'status':'UNKNOWN','explanation':'Choose two faces for distance/planar angle or one face for area'}

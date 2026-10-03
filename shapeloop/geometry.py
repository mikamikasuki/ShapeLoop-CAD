"""CadQuery BREP execution and tessellation. Run only in an isolated worker."""
from __future__ import annotations
import json
import math
from pathlib import Path
import hashlib
import time

MESH_TOLERANCE_MM = 0.15
ANGULAR_TOLERANCE_RAD = 0.15


def _bbox(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    import cadquery as cq
    native = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, native, False, False)
    b = cq.BoundBox(native)
    return {"min":[b.xmin,b.ymin,b.zmin],"max":[b.xmax,b.ymax,b.zmax],"size":[b.xlen,b.ylen,b.zlen],"center":[(b.xmin+b.xmax)/2,(b.ymin+b.ymax)/2,(b.zmin+b.zmax)/2]}


def _box(size, center):
    import cadquery as cq
    if len(size) != 3 or min(size) <= 0: raise ValueError("Box dimensions must be positive")
    return cq.Workplane("XY").box(*size).val().translate(cq.Vector(*center))


def _axis(axis):
    import cadquery as cq
    if axis not in ("X","Y","Z"): raise ValueError("Axis must be X, Y, or Z")
    return cq.Vector(*{"X":(1,0,0),"Y":(0,1,0),"Z":(0,0,1)}[axis])


def _cylinder(diameter, height, center, axis="Z"):
    import cadquery as cq
    if diameter <= 0 or height <= 0: raise ValueError("Cylinder diameter and height must be positive")
    return cq.Solid.makeCylinder(diameter/2, height, cq.Vector(*center), _axis(axis))


def _edge_selection(shape, selector):
    """Geometric predicates re-resolve every build; no cross-revision face indices."""
    b = _bbox(shape); lo,hi=b["min"],b["max"]; tol=1e-5
    result=[]
    for edge in shape.Edges():
        if selector == "all": result.append(edge); continue
        if edge.geomType() != "LINE": continue
        a,c=edge.startPoint().toTuple(),edge.endPoint().toTuple()
        vertical=abs(a[0]-c[0])<tol and abs(a[1]-c[1])<tol and abs(a[2]-c[2])>tol
        extreme_x=abs(a[0]-lo[0])<tol or abs(a[0]-hi[0])<tol
        extreme_y=abs(a[1]-lo[1])<tol or abs(a[1]-hi[1])<tol
        if selector == "vertical" and vertical: result.append(edge)
        elif selector == "outer_vertical" and vertical and (extreme_x or extreme_y): result.append(edge)
        elif selector in ("top_outer","bottom_outer"):
            z=hi[2] if selector=="top_outer" else lo[2]
            if abs(a[2]-z)<tol and abs(c[2]-z)<tol and (extreme_x or extreme_y): result.append(edge)
    if selector not in ("all","vertical","outer_vertical","top_outer","bottom_outer"):
        raise ValueError(f"Unsupported geometric selector {selector!r}; raw face indices are not supported")
    if not result: raise ValueError(f"Reference {selector!r} resolved to no edges")
    return result


def _transform(shape, transform):
    for direction,angle in zip(((1,0,0),(0,1,0),(0,0,1)),transform.get("rotation",[0,0,0])):
        if angle: shape=shape.rotate((0,0,0),direction,angle)
    translation=tuple(transform.get("translation",[0,0,0]))
    return shape.translate(translation) if any(translation) else shape


def construct(runtime, reused=None):
    """Build arbitrary acyclic combinations of the supported semantic features."""
    import cadquery as cq
    nodes={f["id"]:f for f in runtime["features"]}; shapes={}; provenance={}; elapsed={}
    def build_feature(fid):
        if fid in shapes:return shapes[fid]
        f=nodes[fid]; p=f["parameters"]; inputs=[build_feature(x) for x in f["inputs"]]; kind=f["type"]; t=time.monotonic()
        if kind == "box": result=_box(p["size"],p.get("center",[0,0,0]))
        elif kind == "cylinder": result=_cylinder(p["diameter"],p["height"],p.get("center",[0,0,0]),p.get("axis","Z"))
        elif kind == "extrude":
            plane=p.get("plane","XY")
            if plane not in ("XY","XZ","YZ"):raise ValueError("Sketch plane must be XY, XZ or YZ")
            wp=cq.Workplane(plane)
            if p.get("profile","rectangle")=="rectangle": wp=wp.rect(p["width"],p["height"])
            elif p["profile"]=="circle":wp=wp.circle(p["diameter"]/2)
            elif p["profile"]=="polygon":wp=wp.polyline(p["points"]).close()
            else:raise ValueError("Supported sketch profiles: rectangle, circle, polygon")
            if p["depth"]<=0:raise ValueError("Extrusion depth must be positive")
            result=wp.extrude(p["depth"]).val().translate(tuple(p.get("center",[0,0,0])))
        elif kind in ("union","subtract","intersect"):
            if len(inputs)<2:raise ValueError(f"{kind} requires at least two input features")
            result=inputs[0]
            for other in inputs[1:]:result=getattr(result,{"union":"fuse","subtract":"cut","intersect":"intersect"}[kind])(other)
            result=result.clean()
        elif kind in ("pocket","slot"):
            if len(inputs)!=1:raise ValueError(f"{kind} requires one input")
            tool=_box(p["size"],p.get("center",[0,0,0])); result=inputs[0].cut(tool).clean()
        elif kind == "hole":
            if len(inputs)!=1:raise ValueError("Hole requires one input")
            result=inputs[0]; axis=p.get("axis","Z"); direction={"X":0,"Y":1,"Z":2}[axis]
            centers=p.get("centers",[p.get("center",[0,0,0])])
            if not centers or len(centers)>500:raise ValueError("Hole count must be between 1 and 500")
            for center in centers:
                base=list(center);base[direction]=p.get("start",center[direction])
                tool=_cylinder(p["diameter"],p["depth"],base,axis)
                if result.intersect(tool).Volume()<=1e-8:raise ValueError(f"Hole {fid} at {center} does not intersect its input")
                result=result.cut(tool)
            result=result.clean()
        elif kind == "pattern":
            if len(inputs)>1:raise ValueError("Pattern permits zero or one input")
            tools=[]
            centers=p.get("centers")
            if centers is None:
                nx,ny=int(p.get('count_x',1)),int(p.get('count_y',1))
                if nx<1 or ny<1 or nx*ny>500:raise ValueError('Pattern count must be between 1 and 500')
                centers=[[x*p.get("spacing_x",0),y*p.get("spacing_y",0),p.get("z",0)] for x in range(nx) for y in range(ny)]
            if not centers or len(centers)>500:raise ValueError("Pattern count must be between 1 and 500")
            for center in centers:
                center=list(center);center[2]=p.get("z",center[2])
                if p.get("profile","cylinder")=="cylinder":tool=_cylinder(p["diameter"],p["height"],center,p.get("axis","Z"))
                elif p["profile"]=="box":tool=_box(p["size"],center)
                else:raise ValueError("Pattern profile must be cylinder or box")
                tools.append(tool)
            result=inputs[0] if inputs else tools.pop(0)
            for tool in tools:result=result.cut(tool) if p.get("mode","union")=="subtract" else result.fuse(tool)
            result=result.clean()
        elif kind in ("fillet","chamfer"):
            if len(inputs)!=1:raise ValueError(f"{kind} requires one input")
            amount=p["radius" if kind=="fillet" else "length"]
            if amount < 0:raise ValueError("Edge treatment size cannot be negative")
            if amount==0:result=inputs[0]
            else:
                edges=_edge_selection(inputs[0],p.get("selector","outer_vertical"))
                result=inputs[0].fillet(amount,edges) if kind=="fillet" else inputs[0].chamfer(amount,None,edges)
        elif kind == "transform":
            if len(inputs)!=1:raise ValueError("Transform requires one input")
            result=_transform(inputs[0],p)
        elif kind == "import_step":
            path=Path(p["path"])
            if not path.is_file() or path.suffix.lower() not in (".step",".stp"):raise ValueError("Imported reference must be an existing STEP file")
            result=cq.importers.importStep(str(path)).val()
        else:raise ValueError(f"Unsupported feature {kind}")
        if not result.isValid() or not result.Solids() or result.Volume()<=1e-9:
            raise ValueError(f"Feature {fid} produced empty or invalid BREP")
        shapes[fid]=result;elapsed[fid]=time.monotonic()-t
        # Same underlying BREP identities survive only within this build. Newly generated
        # faces receive this operation ID; reused faces keep their construction ID.
        ancestors={}
        for ref in f["inputs"]:
            for old_face,old_feature in provenance[ref]:ancestors[old_face.hashCode()]=(old_face,old_feature)
        provenance[fid]=[]
        for face in result.Faces():
            prior=ancestors.get(face.hashCode())
            provenance[fid].append((face,prior[1] if prior and face.isSame(prior[0]) else fid))
        return result
    parts={}
    for part in runtime["parts"]:
        if reused and part["id"] in reused:
            parts[part["id"]]=reused[part["id"]][0]
            continue
        original=build_feature(part["feature"])
        parts[part["id"]]=_transform(original,part.get("transform",{}))
    return parts,shapes,provenance,elapsed


def _tessellate(shape, part, provenance, transform):
    import cadquery as cq
    positions=[];normals=[];indices=[];triangle_faces=[];faces=[]
    mapping=[(_transform(face,transform),fid) for face,fid in provenance]
    for face_index,face in enumerate(shape.Faces()):
        vertices,triangles=face.tessellate(MESH_TOLERANCE_MM,ANGULAR_TOLERANCE_RAD)
        offset=len(positions)//3; start=len(indices)//3
        sums=[[0.,0.,0.] for _ in vertices]
        for tri in triangles:
            a,b,c=(vertices[i] for i in tri);normal=(b-a).cross(c-a)
            for i in tri:
                sums[i][0]+=normal.x;sums[i][1]+=normal.y;sums[i][2]+=normal.z
            indices.extend(offset+i for i in tri);triangle_faces.append(face_index)
        for v,n in zip(vertices,sums):
            positions.extend(v.toTuple());length=math.sqrt(sum(x*x for x in n)) or 1
            normals.extend(x/length for x in n)
        matches=[fid for candidate,fid in mapping if face.isSame(candidate)]
        if not matches:
            # Rigid transforms duplicate topology; re-resolve against geometric
            # predicates and require a unique match, never reuse raw face indices.
            matches=[fid for candidate,fid in mapping if candidate.geomType()==face.geomType() and abs(candidate.Area()-face.Area())<1e-5 and (candidate.Center()-face.Center()).Length<1e-5 and max(abs(a-b) for a,b in zip(_bbox(candidate)["size"],_bbox(face)["size"]))<1e-5]
        faces.append({"id":f'{part["id"]}:face:{face_index}',"triangle_start":start,"triangle_count":len(triangles),"feature_id":matches[0] if len(matches)==1 else None,"geometry_type":face.geomType(),"center":list(face.Center().toTuple()),"area":face.Area(),"mapping":"construction_provenance" if len(matches)==1 else "unresolved"})
    return {"id":part["id"],"name":part["name"],"color":part.get("color","#58bdb7"),"positions":positions,"normals":normals,"indices":indices,"triangle_faces":triangle_faces,"faces":faces,"bounds":_bbox(shape),"volume":shape.Volume()}




def _runtime_fingerprint(runtime):
    # Imported direct geometry binds to its bytes rather than the installation's
    # absolute filename, so a portable source bundle has the same geometry identity.
    canonical=json.loads(json.dumps(runtime))
    for feature in canonical['features']:
        if feature['type']=='import_step':
            feature['parameters']['path']='sha256:'+hashlib.sha256(Path(feature['parameters']['path']).read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _part_cache_key(runtime, part):
    import cadquery as cq
    import OCP
    nodes={f['id']:f for f in runtime['features']};needed={}
    def include(fid):
        if fid in needed:return
        feature=dict(nodes[fid])
        if feature['type']=='import_step':
            feature=dict(feature,import_sha256=hashlib.sha256(Path(feature['parameters']['path']).read_bytes()).hexdigest())
        needed[fid]=feature
        for ref in feature['inputs']:include(ref)
    include(part['feature'])
    payload={'cache_schema':1,'kernel':{'cadquery':cq.__version__,'ocp':OCP.__version__},'part':part,'dag':[needed[key] for key in sorted(needed)],'mesh_tolerance_mm':MESH_TOLERANCE_MM,'angular_tolerance_rad':ANGULAR_TOLERANCE_RAD}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _read_part_cache(cache, key):
    import cadquery as cq
    folder=cache/key
    try:
        manifest=json.loads((folder/'manifest.json').read_text())
        if manifest['key']!=key or manifest['cache_schema']!=1:return None
        for filename,expected in manifest['files'].items():
            if filename not in ('shape.brep','mesh.json'):return None
            if hashlib.sha256((folder/filename).read_bytes()).hexdigest()!=expected:return None
        if set(manifest['files'])!={'shape.brep','mesh.json'}:return None
        shape=cq.Shape.importBrep(str(folder/'shape.brep'))
        if not shape.isValid() or len(shape.Solids())!=manifest['solids'] or len(shape.Faces())!=manifest['faces']:return None
        if abs(shape.Volume()-manifest['volume'])>max(1e-6,manifest['volume']*1e-9):return None
        mesh=json.loads((folder/'mesh.json').read_text())
        if len(mesh['faces'])!=len(shape.Faces()) or len(mesh['indices'])%3 or len(mesh['positions'])%3:return None
        for face,record in zip(shape.Faces(),mesh['faces']):
            if face.geomType()!=record['geometry_type'] or abs(face.Area()-record['area'])>1e-5 or math.dist(face.Center().toTuple(),record['center'])>1e-5:return None
        return shape,mesh
    except (OSError,ValueError,KeyError,RuntimeError,TypeError):return None


def _write_part_cache(cache,key,shape,mesh):
    import os
    import shutil
    import uuid
    temporary=cache/f'.tmp-{uuid.uuid4().hex}'
    temporary.mkdir()
    try:
        shape.exportBrep(str(temporary/'shape.brep'))
        (temporary/'mesh.json').write_text(json.dumps(mesh))
        manifest={'key':key,'cache_schema':1,'solids':len(shape.Solids()),'faces':len(shape.Faces()),'volume':shape.Volume(),'files':{name:hashlib.sha256((temporary/name).read_bytes()).hexdigest() for name in ('shape.brep','mesh.json')}}
        (temporary/'manifest.json').write_text(json.dumps(manifest))
        target=cache/key
        try:os.rename(temporary,target)
        except OSError:
            # A simultaneous worker may already have published the same valid key.
            # Leave it intact; a corrupt entry is never reused and can be cleaned
            # through the application's explicit storage cleanup operation.
            pass
    finally:
        if temporary.exists():shutil.rmtree(temporary)


def _build_runtime(runtime, output_dir, cache_dir=None):
    import cadquery as cq
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    cache=Path(cache_dir) if cache_dir is not None else None
    reused={};keys={}
    if cache is not None:
        cache.mkdir(parents=True,exist_ok=True)
        for part in runtime["parts"]:
            key=_part_cache_key(runtime,part);keys[part["id"]]=key
            loaded=_read_part_cache(cache,key)
            if loaded is not None:reused[part["id"]]=loaded
    parts,shapes,provenance,elapsed=construct(runtime,reused);metadata=[];meshes=[]
    for part in runtime["parts"]:
        pid=part["id"];shape=parts[pid]
        paths={ext:f"{pid}.{ext}" for ext in ("step","stl","svg")}
        cq.exporters.export(shape,str(out/paths["step"]))
        cq.exporters.export(shape,str(out/paths["stl"]),tolerance=MESH_TOLERANCE_MM,angularTolerance=ANGULAR_TOLERANCE_RAD)
        cq.exporters.export(shape,str(out/paths["svg"]),opt={"projectionDir":(0,0,1),"showHidden":False,"showAxes":False,"width":800,"height":600})
        mesh=reused[pid][1] if pid in reused else _tessellate(shape,part,provenance[part["feature"]],part.get("transform",{}))
        meshes.append(mesh)
        if cache is not None and pid not in reused:_write_part_cache(cache,keys[pid],shape,mesh)
        (out/f"{pid}.mesh.json").write_text(json.dumps(mesh))
        metadata.append({"id":pid,"name":part["name"],**paths,"mesh_file":f"{pid}.mesh.json","bounds":_bbox(shape),"volume":shape.Volume(),"solids":len(shape.Solids()),"sha256":hashlib.sha256((out/paths["step"]).read_bytes()).hexdigest(),"transform":part.get("transform",{}),"feature":part["feature"]})
    compound=cq.Compound.makeCompound(list(parts.values()))
    for ext in ("step","stl","svg"):
        opts={"tolerance":MESH_TOLERANCE_MM,"angularTolerance":ANGULAR_TOLERANCE_RAD} if ext=="stl" else {"opt":{"projectionDir":(0,0,1),"showHidden":False,"showAxes":False,"width":800,"height":600}} if ext=="svg" else {}
        cq.exporters.export(compound,str(out/f"assembly.{ext}"),**opts)
    result={"units":"mm","spec_sha256":_runtime_fingerprint(runtime),"parts":metadata,"bounds":_bbox(compound),"volume":sum(s.Volume() for s in parts.values()),"files":[*['assembly.step','assembly.stl','assembly.svg','mesh.json','metadata.json'],*[f'{p["id"]}.{ext}' for p in runtime["parts"] for ext in ('step','stl','svg','mesh.json')]],"feature_build_seconds":elapsed,"mesh_tolerance_mm":MESH_TOLERANCE_MM,"angular_tolerance_rad":ANGULAR_TOLERANCE_RAD,"cache_reused_parts":sorted(reused)}
    mesh_doc={"units":"mm","tolerance_mm":MESH_TOLERANCE_MM,"angular_tolerance_rad":ANGULAR_TOLERANCE_RAD,"parts":meshes,"bounds":result["bounds"],"identity_scope":"Face and triangle IDs apply only to this revision. Semantic feature IDs are stable."}
    (out/"mesh.json").write_text(json.dumps(mesh_doc));(out/"metadata.json").write_text(json.dumps(result,indent=2))
    return result


def build(spec_dict, output_dir, cache_dir=None):
    from .spec import normalize
    return _build_runtime(normalize(spec_dict),output_dir,cache_dir)

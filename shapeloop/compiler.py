"""Readable, independently rebuildable parametric Python bundles."""
from pathlib import Path
import json
import pprint
from .spec import DesignSpec, normalize


def compile_source(spec: DesignSpec | dict) -> str:
    spec=spec if isinstance(spec,DesignSpec) else DesignSpec.model_validate(spec)
    normalize(spec)  # reject dimension errors before emitting source
    root=Path(__file__).parent
    schema=(root/"spec.py").read_text()
    runtime=(root/"geometry.py").read_text().split('\ndef build(spec_dict, output_dir')[0]
    schema=schema.replace('from __future__ import annotations\n','')
    runtime=runtime.replace('from __future__ import annotations\n','')
    encoded=pprint.pformat(spec.model_dump(mode="json"),width=100,sort_dicts=False)
    return '''#!/usr/bin/env python3
"""ShapeLoop-CAD editable parametric CAD export.
Requirements: Python 3.12, cadquery==2.5.2, pydantic>=2.10,<3.
All manufacturing coordinates and tessellation values are millimeters.
Rebuild: python design.py --output ./rebuilt
Override parameters: python design.py --parameters '{"height":24}' --output ./rebuilt
STEP preserves BREP geometry; this source and DesignSpec preserve parameter intent.
"""
from __future__ import annotations
''' + schema + '\n' + runtime + '\n\nSPEC = ' + encoded + '''

def main():
    import argparse
    parser=argparse.ArgumentParser(description="Independently rebuild ShapeLoop-CAD geometry")
    parser.add_argument("--output",default="rebuilt")
    parser.add_argument("--parameters",default="{}",help="JSON object of named parameter values, or JSON file path")
    parser.add_argument("--spec",help="Optional full DesignSpec JSON file")
    args=parser.parse_args()
    spec=json.loads(Path(args.spec).read_text()) if args.spec else SPEC
    override_path=Path(args.parameters)
    changes=json.loads(args.parameters) if args.parameters.lstrip().startswith("{") else json.loads(override_path.read_text())
    for name,value in changes.items():
        if name not in spec["parameters"]:raise ValueError(f"Unknown parameter {name}")
        spec["parameters"][name]["value"]=value
    for feature in spec["features"]:
        if feature["type"]=="import_step":
            reference=Path(feature["parameters"]["path"])
            if not reference.is_absolute():feature["parameters"]["path"]=str(Path(__file__).resolve().parent/reference)
    validated=DesignSpec.model_validate(spec)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/"design.json").write_text(validated.model_dump_json(indent=2))
    result=_build_runtime(normalize(validated),out)
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
'''

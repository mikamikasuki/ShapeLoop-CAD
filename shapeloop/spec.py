"""Versioned semantic designs and a restricted, dimension checked expression language."""
from __future__ import annotations
import ast
import math
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}
FEATURE_TYPES = {"box", "cylinder", "extrude", "union", "subtract", "intersect", "hole", "pattern", "pocket", "slot", "fillet", "chamfer", "transform", "import_step"}

class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    value: float | str
    dimension: Literal["length", "angle", "number"] = "length"
    unit: str | None = None
    description: str = ""

class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")
    name: str
    type: str
    part: str
    inputs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def finite_parameters(self):
        def check(value):
            if isinstance(value,float) and not math.isfinite(value):raise ValueError('Feature numeric parameters must be finite')
            if isinstance(value,dict):
                for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
        check(self.parameters)
        return self

class Transform(BaseModel):
    translation: list[float | str] = Field(default_factory=lambda: [0.0, 0.0, 0.0], min_length=3, max_length=3)
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], min_length=3, max_length=3)

class Part(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")
    name: str
    feature: str
    transform: Transform = Field(default_factory=Transform)
    color: str = "#58bdb7"

class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str
    name: str
    type: str
    required: bool = True
    features: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    tolerance: float = Field(default=0.01,ge=0)

class DesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    version: Literal["1.0"] = "1.0"
    name: str = "Untitled design"
    family: str = "custom"
    units: Literal["mm", "cm", "m", "in", "inch"] = "mm"
    parameters: dict[str, Parameter] = Field(default_factory=dict)
    parts: list[Part]
    datums: dict[str, Any] = Field(default_factory=lambda: {"origin": {"origin": [0, 0, 0], "axes": "XYZ"}})
    features: list[Feature]
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    objectives: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self):
        for parameter_name in self.parameters:
            if not parameter_name.isidentifier() or parameter_name in {*UNITS,"deg","rad"}:
                raise ValueError(f"Invalid or reserved parameter name {parameter_name}")
        ids = [f.id for f in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("Feature IDs must be unique")
        parts = [p.id for p in self.parts]
        if len(parts) != len(set(parts)) or not parts:
            raise ValueError("Part IDs must be unique and nonempty")
        graph = {f.id: f.inputs for f in self.features}
        for f in self.features:
            if f.type not in FEATURE_TYPES:
                raise ValueError(f"Unsupported feature type: {f.type}")
            if f.part not in parts:
                raise ValueError(f"Feature {f.id} references missing part {f.part}")
            for ref in f.inputs:
                if ref not in graph:
                    raise ValueError(f"Feature {f.id} references missing feature {ref}")
        visiting, visited = set(), set()
        def visit(key):
            if key in visiting:
                raise ValueError(f"Feature dependency cycle at {key}")
            if key in visited: return
            visiting.add(key)
            for ref in graph[key]: visit(ref)
            visiting.remove(key); visited.add(key)
        for key in graph: visit(key)
        for p in self.parts:
            if p.feature not in graph: raise ValueError(f"Part {p.id} references missing feature {p.feature}")
            if next(f.part for f in self.features if f.id == p.feature) != p.id:
                raise ValueError(f"Part {p.id} output belongs to another part")
        for c in self.constraints:
            for ref in c.features:
                if ref not in graph and ref not in parts:
                    raise ValueError(f"Constraint {c.id} references missing feature {ref}")
        if len({c.id for c in self.constraints}) != len(self.constraints):
            raise ValueError("Constraint IDs must be unique")
        resolve_parameters(self)
        return self


def _expression(text: str, lookup) -> tuple[float, str]:
    """No calls, attributes, indexing, strings, or arbitrary Python execution."""
    if len(text) > 300: raise ValueError("Expression too long")
    try: tree = ast.parse(re.sub(r"\bin\b", "inch", text), mode="eval")
    except SyntaxError as exc: raise ValueError("Invalid dimension expression") from exc
    def walk(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value), "number"
        if isinstance(n, ast.Name): return lookup(n.id)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            value, dim = walk(n.operand); return (-value if isinstance(n.op, ast.USub) else value), dim
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, da = walk(n.left); b, db = walk(n.right)
            if isinstance(n.op, (ast.Add, ast.Sub)):
                if da != db: raise ValueError(f"Cannot add/subtract {da} and {db}")
                return (a+b if isinstance(n.op, ast.Add) else a-b), da
            if isinstance(n.op, ast.Mult):
                if da != "number" and db != "number": raise ValueError("Multiplication of two dimensions is outside supported expressions")
                return a*b, db if da == "number" else da
            if b == 0: raise ValueError("Division by zero")
            if db == "number": return a/b, da
            if da == db: return a/b, "number"
            raise ValueError("Unsupported dimensional division")
        raise ValueError("Only names, numeric constants, + - * / and parentheses are allowed")
    value, dim = walk(tree.body)
    if not math.isfinite(value): raise ValueError("Expression must be finite")
    return value, dim


def resolve_parameters(spec: DesignSpec) -> dict[str, tuple[float, str]]:
    result, active = {}, set()
    def lookup(key):
        if key in UNITS: return UNITS[key], "length"
        if key == "deg": return 1.0, "angle"
        if key == "rad": return 180/math.pi, "angle"
        if key in result: return result[key]
        if key not in spec.parameters: raise ValueError(f"Unknown parameter {key}")
        if key in active: raise ValueError(f"Parameter dependency cycle at {key}")
        active.add(key); p = spec.parameters[key]
        if p.dimension == "angle" and p.unit not in (None,"deg","rad"):raise ValueError(f"Unsupported angle unit {p.unit}")
        if p.dimension == "number" and p.unit is not None:raise ValueError("Dimensionless parameter cannot have a unit")
        if isinstance(p.value, (float,int)):
            factor = UNITS.get(p.unit or spec.units, 1) if p.dimension == "length" else (180/math.pi if p.unit == "rad" else 1)
            if p.dimension == "length" and (p.unit or spec.units) not in UNITS: raise ValueError(f"Unsupported length unit {p.unit}")
            value, dim = float(p.value)*factor, p.dimension
        else:
            value, dim = _expression(p.value, lookup)
            if dim == "number" and p.dimension != "number":
                value *= UNITS[p.unit or spec.units] if p.dimension == "length" else 1
                dim = p.dimension
        if dim != p.dimension: raise ValueError(f"Parameter {key}: expected {p.dimension}, got {dim}")
        if not math.isfinite(value): raise ValueError(f"Parameter {key} is not finite")
        active.remove(key); result[key] = value, dim
        return result[key]
    for key in spec.parameters: lookup(key)
    return result

NUMBER_KEYS = {"count", "count_x", "count_y", "index", "segments", "expected_solids", "allowed_contact", "max_volume", "volume_tolerance", "number_tolerance", "required", "enabled"}
ANGLE_KEYS = {"angle", "rotation", "angular_tolerance"}
TEXT_KEYS = {"axis", "plane", "selector", "path", "part", "parts", "feature", "other", "mode", "profile", "method", "frame", "region", "reference", "allowed_contacts", "description", "direction"}

def normalize(spec: DesignSpec | dict) -> dict:
    spec = spec if isinstance(spec, DesignSpec) else DesignSpec.model_validate(spec)
    values = resolve_parameters(spec)
    def resolve(value, dimension="length", key=""):
        if key in TEXT_KEYS: return value
        if isinstance(value, bool) or value is None: return value
        if isinstance(value, dict): return {k: resolve(v, "number" if k in NUMBER_KEYS else "angle" if k in ANGLE_KEYS else "length", k) for k,v in value.items()}
        if isinstance(value, list): return [resolve(v, dimension, key) for v in value]
        if isinstance(value, (float,int)):
            if not math.isfinite(value):raise ValueError(f"Feature field {key} must be finite")
            if key in {"count","count_x","count_y","expected_solids"} and (float(value)!=int(value) or value<1):raise ValueError(f"Feature field {key} must be a positive integer")
            return float(value)*UNITS[spec.units] if dimension == "length" else float(value)
        if isinstance(value, str):
            try: val,dim = _expression(value, lambda n: values[n] if n in values else (UNITS[n], "length") if n in UNITS else (1.0,"angle") if n == "deg" else (180/math.pi,"angle") if n == "rad" else (_ for _ in ()).throw(ValueError(f"Unknown parameter {n}")))
            except KeyError as exc: raise ValueError(f"Unknown parameter {exc}") from exc
            if dim == "number" and dimension != "number": val *= UNITS[spec.units] if dimension == "length" else 1; dim = dimension
            if dim != dimension: raise ValueError(f"Feature field {key}: expected {dimension}, got {dim}")
            if key in {"count","count_x","count_y","expected_solids"} and (val!=int(val) or val<1):raise ValueError(f"Feature field {key} must be a positive integer")
            return val
        raise ValueError(f"Unsupported parameter value {value!r}")
    data = spec.model_dump(mode="python")
    data["resolved_parameters"] = {key:value for key,(value,_) in values.items()}
    data["internal_units"] = "mm"
    for datum in data["datums"].values():
        if isinstance(datum,dict) and "origin" in datum:datum["origin"] = resolve(datum["origin"])
    for f in data["features"]: f["parameters"] = resolve(f["parameters"])
    for p in data["parts"]:
        p["transform"]["translation"] = resolve(p["transform"]["translation"])
    for c in data["constraints"]:
        c["parameters"] = resolve(c["parameters"])
        # Volume thresholds are explicitly mm³ and count tolerances are numeric;
        # only length-based contract tolerances follow display length units.
        if c["type"] not in ("keepout","brep"):
            c["tolerance"] *= UNITS[spec.units]
    return data

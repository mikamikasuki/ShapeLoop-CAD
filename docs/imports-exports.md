# Imports and exports

STEP input is staged as an explicit direct-geometry part. It supplies BREP geometry, not the original author's feature history. STL input is stored as a mesh reference; it does not become recovered parametric geometry or inherit solid checks. Files are uploaded into the application's import directory rather than read from arbitrary paths supplied to the API.

Exports belong to an exact revision. The worker writes per-part STEP and STL, assembled STEP, real BREP-derived viewport mesh, supported orthographic SVG, semantic JSON, parameters, source, and measured reports. The service checks revision/file manifests before serving artifacts or accepting a candidate. A stale export cannot be substituted for a new failed request.

The source bundle includes `design.py`, `design.json`, `parameters.json`, `REBUILD.txt`, and geometry/report artifacts. Rebuild outside the server:

```sh
python design.py --output rebuilt
python design.py --parameters parameters.json --output rebuilt
```

The exported source needs Python 3.12, CadQuery 2.5.2, and Pydantic 2.x. It contains its dimension parser and geometry construction, so it has no dependency on unpublished ShapeLoop-CAD modules. Keep uploaded reference STEP with a source bundle that uses an imported part; a bare path to the original private import directory is not portable.

All manufacturing coordinates and assembly transforms are expressed internally in millimeters. STL does not encode this convention reliably; choose millimeters when importing it into another tool. Preview visibility, orbit, camera projection, and comparison overlay do not alter exported part placement.

STEP preserves solid geometry and placement rather than complete parametric intent. Keep source and DesignSpec with it for editable history. SVG is an orthographic geometric projection for the supported view; it does not certify drafting standards or manufacturing completeness. The verifier reopens actual STEP and compares BREP quantities before acceptance.

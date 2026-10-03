# ShapeLoop-CAD

ShapeLoop-CAD is a local parametric CAD workbench for editing mechanical parts while measuring the geometry that must stay fixed. Enclosures, mounting plates, and orthogonal brackets are editable starting recipes. A validated feature graph builds real CadQuery/OCCT BREP; a separate worker reopens STEP and checks required dimensions before a candidate can be accepted.

## Start

Use Python 3.12 and Node.js 22 or newer for a source checkout:

```sh
git clone https://github.com/mikamikasuki/ShapeLoop-CAD.git
cd ShapeLoop-CAD
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install -e '.[dev]'
npm --prefix frontend ci
npm --prefix frontend run build
shapeloop-cad doctor
shapeloop-cad serve
```

Open the local URL printed by `serve`. Application data defaults to `~/.local/share/shapeloop`; set `SHAPELOOP_DATA_DIR` to use another directory. The service binds to loopback by default. Keep the session token local.

The native environment exercised during development is macOS ARM64, Python 3.12.14, CadQuery 2.5.2, cadquery-ocp 7.7.2, NumPy 2.5.3, NLopt 2.11.0, and CasADi 3.8.1. A fresh virtual environment installed the built wheel and passed doctor, enclosure editing/checking, STEP and bundle export, standalone source rebuild, and bundled UI/API serving. `doctor` performs a real primitive build, STEP export, and reimport. Other operating systems and the container recipe need their own checks; native wheel availability is platform dependent.

## Workflow

Create a recipe, edit parameters or features, inspect the measured report, compare the candidate with the accepted revision, and accept or reject it. A failed candidate leaves the last accepted revision available. Required results are `PASS`, `FAIL`, or `UNKNOWN`; unsupported measurements cannot pass acceptance.

The enclosure starts at 80 × 50 × 30 mm **including its separate closed 2 mm lid**. Its four mounting axes are named relative to the origin datum. Features include bosses, holes, rectangular connector cuts, slots, and supported edge treatments. New feature arrangements are represented in the semantic graph rather than selected from fixed output meshes.

Structured editing, geometry checking, branches, and exports work without a model. Natural-language generation and editing require an explicitly configured OpenAI-compatible endpoint and model. Credentials remain in the backend. No provider or model is selected automatically; see [providers](docs/providers.md).

SolutionScout indexes selected official documentation and CadQuery source/tests, searches the local cache first, and can reproduce a narrow remedy on three disposable box variants. Network access and watch refresh are opt-in. Cards distinguish sourced, reproduced, rejected, and stale guidance. Lookup works without a model; a configured provider and positive budget enable separately labeled source-grounded hypotheses. See [SolutionScout](docs/scout.md).

## Commands and exports

```sh
shapeloop-cad new --recipe enclosure --project /tmp/my-enclosure
shapeloop-cad edit --project /tmp/my-enclosure --set height=24 --accept
shapeloop-cad check --project /tmp/my-enclosure
shapeloop-cad export --project /tmp/my-enclosure --format bundle --output /tmp/enclosure.zip
shapeloop-cad demo
shapeloop-cad benchmark
shapeloop-cad scout sync --network
shapeloop-cad scout ask fillet --network
```

Use `shapeloop-cad --help` and each subcommand's help for project, revision, and output options. The API and CLI share the same project service. STEP and STL come from the built BREP. Export bundles contain an editable DesignSpec, named parameters, a self-contained CadQuery Python program, and measured reports. Rebuild a downloaded source bundle with `python design.py --output rebuilt`; no ShapeLoop-CAD server is needed.

STL coordinates are millimeters; STL does not intrinsically store a reliable unit declaration. STEP import is direct/reference geometry and does not recover the original feature tree. SVG is a supported orthographic projection, not a standards-certified manufacturing drawing. See [imports and exports](docs/imports-exports.md).

## Development and scope

```sh
python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Geometry generation and verification share the same kernel. Supported wall checks identify named planar regions; there is no global minimum-wall guarantee, FEA, load rating, printing certification, or physical-fit validation. Live-model success requires a configured provider and is separate from mock transport tests. Read [constraints](docs/constraints.md), [editing](docs/editing.md), [validation](docs/validation.md), and [known limitations](docs/limitations.md).

Original ShapeLoop-CAD code is Apache-2.0. Dependencies retain their licenses, including native copyleft components and a restrictive METIS 4 notice in the tested CasADi wheel. The source checkout does not bundle CAD binaries; do not infer that the whole native runtime is Apache-2.0 or unrestricted for binary redistribution. See [third-party notices](THIRD_PARTY_NOTICES.md) and the [native dependency review](docs/dependency-review.md).

The Dockerfile targets Linux AMD64 and has not been validated. Build it with `docker build --platform linux/amd64 -t shapeloop-cad .`, then run `docker run --rm --platform linux/amd64 -p 127.0.0.1:8765:8765 -v shapeloop-data:/data shapeloop-cad`. The container uses an internal `0.0.0.0` bind; the explicit loopback port mapping keeps access local. A prebuilt image is not distributed.

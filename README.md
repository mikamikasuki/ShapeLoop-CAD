<div align="center">

# ShapeLoop-CAD

### Change the design. Keep the requirements.

A local-first CAD workbench for humans and AI.<br>
Create editable geometry, preserve design intent, and verify every revision.

[![Original code: Apache-2.0](https://img.shields.io/badge/Original_code-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square)](pyproject.toml)
[![CadQuery / OCCT](https://img.shields.io/badge/Geometry-CadQuery%20%2F%20OCCT-5865F2?style=flat-square)](ARCHITECTURE.md)

[Quickstart](#quickstart) · [Design workflow](#a-design-workflow-you-can-inspect) · [Architecture](ARCHITECTURE.md) · [Documentation](#documentation)

</div>

---

> “Make the enclosure shorter. Keep the mounting holes fixed. Preserve room for the electronics.”

Mechanical design evolves through changes like these. A smaller housing still needs the same mounting interface. A new connector opening must leave clearance for internal components. An alternative lid should remain comparable with the original.

**ShapeLoop-CAD makes those requirements part of the design.** Edits produce candidate revisions, real geometry is rebuilt, and a separate worker measures the exported STEP before acceptance. The result includes editable CAD, a measured report, and a history of what changed.

## The product
<img width="1440" height="960" alt="ac209851-539e-41cb-b724-b6d5b8bcc2c1" src="https://github.com/user-attachments/assets/55d66513-efd6-4243-be1e-5f24aebe660d" />


| Capability | What it gives you |
| --- | --- |
| **Parametric design** | Named dimensions, semantic features, explicit datums, and a composable feature graph. |
| **Measured acceptance** | Checks against actual BREP geometry for supported dimensions, mounting patterns, thickness regions, clearances, and interference. |
| **Continuous editing** | Add, move, update, or remove supported features while retaining explicit requirements. |
| **Revision control** | Branch, compare, accept, reject, undo, and redo. Failed candidates remain inspectable alongside the accepted design. |
| **AI-assisted workflows** | English and Chinese generation/editing through a configured model, with validated proposals and bounded repair attempts. |
| **Portable geometry** | STEP, STL, orthographic SVG, DesignSpec, measured reports, and self-contained parametric Python source. |

### A complete workbench

The browser brings the design tree, 3D viewport, parameters, requirements, intent, and revision history into one workspace.

- Inspect actual BREP tessellation with orbit, pan, zoom, standard views, and perspective or orthographic projection.
- Select geometry and request supported BREP measurements.
- Compare revisions in the same coordinate frame.
- Explore an exploded assembly preview while exports retain the assembly’s design positions.
- Save projects, recover completed work after restart, and cancel or retry geometry jobs.

Structured editing and exports work without a model.

## A design workflow you can inspect

The implemented enclosure workflow starts at **80 × 50 × 30 mm, including a separate closed lid**, with four named mounting holes.

1. **Reduce height to 24 mm** while preserving mounting coordinates and hole diameters.
2. **Add and move a connector opening** without changing unrelated features.
3. **Adjust a supported fillet** and inspect the resulting geometry.
4. **Add ventilation slots** while checking the named component keep-out.
5. **Branch the design** into an alternative lid arrangement and compare revisions.
6. **Submit a conflicting requirement** and inspect the measured failure.
7. **Undo, reopen, and export**, then rebuild the exported source independently.

Every required check returns **PASS**, **FAIL**, or **UNKNOWN**, with measurements, units, tolerances, references, and an explanation. A failed or unresolved required check blocks acceptance.

## How it works

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/8cc4ce6d-5063-4b70-a748-0f686c9a9c5d" />


The **DesignSpec** records parameters, parts, datums, feature dependencies, requirements, assumptions, and optional objectives. Semantic IDs identify design features across edits; geometric references are resolved again when topology changes.

The verifier reopens exported STEP and measures the resulting geometry. Unchanged complete parts can reuse validated cached artifacts, while acceptance still requires full verification.

The browser and CLI share the same domain service. FastAPI handles local requests, SQLite persists revisions and jobs, and separate worker processes contain geometry failures and resource limits.

[Explore the architecture →](ARCHITECTURE.md)

## Three starting families. Composable features.

| Family | Starting geometry |
| --- | --- |
| **Electronics enclosures** | Separate lids, mounting bosses, hole patterns, connector openings, and ventilation slots. |
| **Mounting plates** | Editable hole layouts, pockets, slots, and edge treatments. |
| **Orthogonal brackets** | Base and flange geometry, mounting holes, and supported fillets or chamfers. |

Recipes are editable starting points. The feature vocabulary includes primitives, supported sketch extrusions, Boolean operations, patterns, holes, pockets, rectangular slots, edge treatments, and transforms.

STEP can be imported as direct or reference geometry. STL can be retained as a mesh reference.

## AI proposes. Geometry determines acceptance.

Connect a user-managed local inference server or an OpenAI-compatible remote endpoint for natural-language generation and editing.

The model returns a structured DesignSpec or EditProposal. ShapeLoop-CAD validates it, builds a candidate, measures the geometry, and exposes any conflicts before acceptance. Provider credentials remain in the backend.

[Configure a provider →](docs/providers.md)

### SolutionScout

SolutionScout maintains a version-aware library of official documentation, relevant source/tests, and local geometry reproductions.

It searches cached guidance first, can retrieve selected sources with bounded network access, and reproduces supported mechanisms on disposable minimal models. Cards distinguish **sourced**, **reproduced**, **rejected**, and **stale** guidance.

Network access and background refresh are opt-in. Guidance retains its sources, outcomes, and applicability limits; it cannot silently change an accepted design.

[Explore SolutionScout →](docs/scout.md)

## Validation you can reproduce

The exercised validation includes:

- **15 generated multi-edit sequences** across all three mechanical families.
- **135 benchmark candidates** comparing three structured editing policies.
- Negative checks for moved or deleted holes, stale exports, forbidden overlap, and failing BREP behind a valid-looking mesh.
- Real browser workflows covering editing, failed candidates, revision comparison, measurement, and STEP export/reimport.
- Fresh wheel installation and independent reconstruction from exported Python source.

```sh
shapeloop-cad doctor
shapeloop-cad demo
shapeloop-cad benchmark
```

[Read the validation record →](docs/validation.md)

## Quickstart

Requires **Python 3.12** and **Node.js 22.12+**.

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

Open the local URL printed by `serve`.

Projects and artifacts default to `~/.local/share/shapeloop`. Set `SHAPELOOP_DATA_DIR` to choose another directory. The service binds to loopback by default.

### Try a complete CLI edit

```sh
shapeloop-cad new \
  --recipe enclosure \
  --project /tmp/my-enclosure

shapeloop-cad edit \
  --project /tmp/my-enclosure \
  --set height=24 \
  --accept

shapeloop-cad check \
  --project /tmp/my-enclosure

shapeloop-cad export \
  --project /tmp/my-enclosure \
  --format bundle \
  --output /tmp/enclosure.zip
```

The bundle contains the DesignSpec, named parameters, geometry, reports, and parametric source. After extracting it, rebuild with the documented CadQuery/Pydantic dependencies:

```sh
python design.py --output rebuilt
```

## Documentation

| Guide | Focus |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Semantic design, workers, persistence, and acceptance. |
| [Constraints](docs/constraints.md) | Supported measurements, tolerances, and uncertainty. |
| [Editing](docs/editing.md) | Features, proposals, branches, and revisions. |
| [Providers](docs/providers.md) | Model configuration and integration boundaries. |
| [Imports and exports](docs/imports-exports.md) | Geometry interchange and independent rebuilds. |
| [SolutionScout](docs/scout.md) | Sources, reproductions, budgets, and freshness. |
| [Security](SECURITY.md) | Local service and credential boundaries. |

## Contributing

Contributions are welcome in supported CAD operations, geometric verification, semantic references, workbench interaction, and reproducible model evaluation.

```sh
python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance. Report reproducible issues through [GitHub Issues](https://github.com/mikamikasuki/ShapeLoop-CAD/issues).

## License

Original ShapeLoop-CAD code is licensed under **Apache-2.0**.

Dependencies retain their own licenses.

See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md), and the [dependency review](docs/dependency-review.md).

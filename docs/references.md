# Primary reference review

ShapeLoop-CAD's implementation uses public library APIs. The following application/reference mechanisms informed its boundaries; reference applications are not runtime dependencies or bundled code/assets.

| Primary source | Mechanism or finding |
| --- | --- |
| [goal-driven](https://github.com/lidangzzz/goal-driven) | Separate proposal/generation from acceptance |
| [MIT synthesis lecture 17](https://people.csail.mit.edu/asolar/SynthesisCourse/Lecture17.htm) | Counterexamples guide a subsequent candidate rather than becoming an unmeasured critique |
| [CadQuery source](https://github.com/CadQuery/cadquery), [tests](https://github.com/CadQuery/cadquery/blob/master/tests/test_cadquery.py) | Parametric BREP construction, selection, fillet and interchange APIs |
| [CadQuery installation](https://cadquery.readthedocs.io/en/latest/installation.html) | Python/native-wheel compatibility must be verified with a real kernel check |
| [Assemblies](https://cadquery.readthedocs.io/en/latest/assy.html) | Placement and constraints are separate from viewport camera/display state |
| [Interchange](https://cadquery.readthedocs.io/en/latest/importexport.html) | Actual STEP/STL export and STEP reimport; source/history remain separate |
| [Selectors](https://cadquery.readthedocs.io/en/latest/selectors.html) | Geometric selection has construction-specific scope |
| [OpenCascade overview](https://dev.opencascade.org/doc/overview/html/) | Native Boolean/geometry operations and kernel limitations |
| [Three.js docs](https://threejs.org/docs/) | BREP tessellation is rendered as mesh for interaction, not used as the dimensional verifier |
| [CADAM](https://github.com/Adam-CAD/CADAM), [license](https://github.com/Adam-CAD/CADAM/blob/master/LICENSE) | Reference-only interaction review. Its distribution is GPL-3.0; no application UI, prompts, assets, or OpenSCAD runtime are incorporated |
| [agentcad runtime](https://github.com/jdilla1277/agentcad/blob/main/pyproject.toml), [license](https://github.com/jdilla1277/agentcad/blob/main/LICENSE) | Current 0.6.0 defaults to build123d with CadQuery optional; its execute/inspect/export workflow is reference-only. ShapeLoop-CAD uses CadQuery directly |

Local validation covers the installed CadQuery APIs rather than assuming current upstream documentation exactly matches the pinned older wheel. Scout cards retain the source snapshot and exact installed reproduction versions; upstream changes invalidate applicability.

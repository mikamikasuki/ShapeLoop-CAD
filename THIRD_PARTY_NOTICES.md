# Third-party notices

Original ShapeLoop-CAD code is licensed under [Apache-2.0](LICENSE). Third-party packages and native libraries retain their own licenses. The source distribution contains original application code, frontend assets, and upstream license notices; it does not contain downloaded CAD wheels, reference application code, or native CAD binaries.

## Direct runtime dependencies

| Package | Tested version | License / notice |
| --- | --- | --- |
| CadQuery | 2.5.2 | Apache-2.0 |
| cadquery-ocp | 7.7.2 | Apache-2.0 binding; bundled libraries have separate terms |
| OpenCascade within OCP | Installed wheel native stack | LGPL-2.1 with its upstream exception/notice; see the wheel's full bundled notices |
| CasADi | 3.8.1 | LGPL-3.0-or-later plus separate bundled solver licenses |
| NumPy | 2.5.3 | BSD-3-Clause and bundled 0BSD/MIT/Zlib/CC0 notices |
| NLopt | 2.11.0 | MIT |
| ezdxf | 1.4.4 | MIT |
| FastAPI | 0.115.12 | MIT |
| Uvicorn | 0.34.2 | BSD-3-Clause |
| Pydantic / pydantic-core | 2.11.4 / 2.33.2 | MIT |
| Typer | 0.15.3 | MIT |
| HTTPX / HTTP Core | 0.28.1 / 1.0.9 | BSD-3-Clause |
| python-multipart | 0.0.20 | Apache-2.0 |
| React / React DOM | 19.1.1 | MIT |
| Three.js | 0.180.0 | MIT |
| React Three Fiber / Drei | 9.4.0 / 10.7.6 | MIT |
| lucide-react | 0.468.0 | ISC |

Full installed Python notices are retained under [docs/licenses/python](docs/licenses/python), indexed by [python-index.json](docs/licenses/python-index.json). Installed frontend runtime package notices are under [docs/licenses/frontend](docs/licenses/frontend), indexed by [frontend-index.json](docs/licenses/frontend-index.json). These inventories include transitive packages. Missing standalone npm license files are supplemented from the exact source release where available, or explicitly identified as a current upstream supplement/published declaration. Package declarations and upstream notices should be rechecked when locks change.

## Native distribution boundary

The tested macOS ARM64 OCP wheel's `LICENSES_bundled` contains copyleft components including FFmpeg, x264/x265, Qt, and OpenCascade. Their terms are not replaced by ShapeLoop-CAD's original-code license. The installed CasADi wheel also ships `libcoinmetis.2.dylib`; its retained METIS 4.0.3 notice restricts categories of use and redistribution. The solver dependency chain is documented in the [native dependency review](docs/dependency-review.md).

The install instructions fetch these upstream packages separately. No unrestricted binary-redistribution or legally certified combined-runtime claim is made. Publishing an environment image or bundling native wheels needs a separate resolution of the exact native notices and any required permissions/source obligations. Merely avoiding a solver at runtime does not remove the fact that its binary is present in an upstream wheel.

## Reference-only sources

[CADAM](https://github.com/Adam-CAD/CADAM) is a GPL-3.0 reference application; its code, UI, prompts, assets, and OpenSCAD runtime are not incorporated. [agentcad](https://github.com/jdilla1277/agentcad) is an Apache-2.0 reference application; it is not a runtime dependency. [goal-driven](https://github.com/lidangzzz/goal-driven), the [MIT synthesis lecture](https://people.csail.mit.edu/asolar/SynthesisCourse/Lecture17.htm), and the documentation listed in [references](docs/references.md) are consulted as mechanism/source evidence.

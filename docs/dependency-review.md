# Native dependency review

The application license applies to original ShapeLoop-CAD source. This review records evidence from the installed macOS ARM64 environment and exact upstream build sources; it does not certify legal clearance for a combined binary distribution.

## Tested authoring stack

Python 3.12.14, CadQuery 2.5.2, cadquery-ocp 7.7.2, NumPy 2.5.3, NLopt 2.11.0, and CasADi 3.8.1 were installed as compatible native wheels and exercised by a primitive build/export/reimport. ShapeLoop-CAD authors CAD through CadQuery public APIs. It does not install build123d, OpenSCAD, CADAM, or agentcad.

OCP's binding has an Apache-2.0 notice; OpenCascade and the libraries bundled in that wheel have their own terms. The wheel's retained `LICENSES_bundled` lists OCCT LGPL-2.1, Qt LGPL-3.0, FFmpeg GPL-2.0-or-later, x264/x265 GPL-2.0-or-later, and many permissive components. A top-level package classifier is therefore insufficient to characterize the complete native distribution. The full installed notices are preserved in `docs/licenses/python/cadquery-ocp/cadquery_ocp-7.7.2.dist-info/`.

## CasADi / METIS evidence

The installed CasADi wheel carries LGPL-3.0-or-later for CasADi and separate solver notices. It contains `libcoinmetis.2.dylib`, a `coinmetis.pc` declaration for ThirdParty-Metis 2.0.0, and a METIS header whose title identifies METIS 4.0.3. The package's retained `metis-external/metis-4.0/LICENSE` restricts educational/research categories and redistribution; the separate build-harness license does not establish a replacement license for that upstream source.

The [CasADi 3.8.1 CMake configuration](https://github.com/casadi/casadi/blob/3.8.1/CMakeLists.txt) selects `jgillis/ThirdParty-Metis` branch `bugfix2`; that branch's [download recipe](https://github.com/jgillis/ThirdParty-Metis/blob/bugfix2/get.Metis) retrieves METIS 4.0.3. Local `otool -L` confirms `libipopt` links to `libcoinmumps` and `libcoinmetis`; `libcoinmumps` also links to `libcoinmetis`. This is a shipped binary, not only an unused license/header entry.

After importing CadQuery and building a box, the host's loaded-image inventory contained `_casadi.so` and `libcasadi`, but no Ipopt, MUMPS, or METIS image. ShapeLoop-CAD's supported feature construction and explicit part transforms do not invoke an assembly constraint optimizer. This observation narrows the exercised runtime path; it does not establish permission to redistribute the solver binaries that remain present in the upstream wheel.

The current source checkout installs upstream wheels through pip and does not redistribute native binaries or a prebuilt container image. Before doing so, resolve the METIS notice with upstream/rights-holder evidence, or construct and test a native dependency profile that omits that solver stack. A different wheel/profile must pass the real doctor, geometry, export/reimport, and acceptance tests before replacing the documented pinned profile.

## Rechecking a dependency change

Review the actual installed wheel's metadata and bundled licenses, not only repository HEAD or a Python package's top-level SPDX classifier. Inspect native library links and distinguish installed, loaded, and actually invoked solver/plugin code. Preserve upstream notices in distributions. Keep source application license claims separate from native distribution obligations and reference-only application licenses.

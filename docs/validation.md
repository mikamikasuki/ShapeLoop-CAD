# Validation

The exercised native platform is macOS 15.0.1 ARM64 with Python 3.12.14, CadQuery 2.5.2 and OCP 7.7.2. Geometry generation and verification share that kernel; these checks do not establish physical fit, strength or manufacturing certification.

## Geometry and state

The test suite generates fifteen multi-edit sequences across enclosures, plates and brackets. Real STEP checks cover envelope, hole diameter/count/axis/positions, supported thickness probes, keep-out volume and containment, clearance, assembly overlap, topology changes and datum/unit conversion. Negative cases alter hole geometry without changing parameter labels, delete required holes, swap exports, introduce forbidden overlap and pair a valid mesh with an invalid BREP. Additional tests cover missing references, stale edits, required unknowns, cancellation, worker timeout, restart, cache corruption and independently rebuilt sources.

The sequential enclosure demo starts at 80 × 50 × 30 mm including the separate lid, reduces height to 24 mm, adds and moves a connector cut, changes a fillet, adds ventilation, branches the lid arrangement, reports an impossible fixed-component requirement, undoes and reopens the project. Exported source reconstructs the measured envelope and volume. Plate and bracket workflows change dimensions/layouts and insert slots.

## Browser and installation

Two Playwright workflows use the real local backend. They create/edit an enclosure, inspect measured mounting requirements, retain accepted geometry after a failed candidate, compare revisions, download/reimport a valid STEP, undo/reload/redo, measure a selected STEP face and import/reopen an STL reference. Eight frontend tests and the production build pass. The development dependency audit reports zero advisories for the installed npm dependency tree; this is not a security certification.

The Python wheel bundles frontend assets and their notices. A fresh Python 3.12 environment outside the checkout exercises primitive doctor, project creation, structured editing, fresh STEP verification, export, independently rebuilt source and packaged HTTP/JS/CSS resources.

The Linux AMD64 Docker recipe remains unverified: local Docker reported containerd metadata/blob input/output errors during the build attempt. Windows and native Linux/ARM operation were not exercised.

## Structured policy evaluation

The benchmark generates fifteen sequences and executes 135 candidates: 45 requested edits for each of full regeneration, unchecked sequential editing and ShapeLoop-CAD. Full regeneration applies accumulated intent from the recipe. Each sequence ends with a deliberately conflicting mounting edit. The harness reports geometry checks for all policies; ShapeLoop-CAD gates acceptance on them.

| Policy | Preserved mounting checks in retained state | Requested edits achieved | Invalid candidates retained |
| --- | ---: | ---: | ---: |
| Full regeneration | 40 / 60 | 45 / 45 | 15 |
| Unchecked sequential edits | 40 / 60 | 45 / 45 | 15 |
| ShapeLoop-CAD | 60 / 60 | 30 / 45 | 0 |

The fifteen unmet ShapeLoop-CAD requests are the deliberately contradictory edits. The results demonstrate the implemented acceptance policy on generated structured inputs. They do not establish model quality, broad product superiority or human usability. All policies use the same installed CadQuery stack; ShapeLoop-CAD may reuse unaffected parts but always revalidates every required check. Wall times and per-candidate records are measured at runtime rather than committed as fixture tables.

## Providers and Scout

Live Scout retrieval downloads relevant official CadQuery source/tests. Fillet, selector, Boolean and STEP mechanisms are actually reproduced on three fixed disposable box variants each. Byte limits, offline cache use, source/version invalidation, scheduler cancellation and the boundary between advice and accepted edits are tested.

No provider was configured for validation. Natural-language generation/editing, bounded model repairs and optional model-assisted Scout inference are implemented, with structured-output and error/cancellation behavior tested through mock transports. Their live-model success and token costs remain unexercised. Source lookup and all structured CAD workflows remain functional without a model.

# SolutionScout

SolutionScout is a persistent source index and narrow reproduction library. Enable network access, select sources, and sync to create the initial index. With network disabled, it uses the existing cache and reports freshness as a cached snapshot. An empty offline cache produces an explicit unresolved result.

Default sources are CadQuery selectors, interchange, assembly and class documentation, plus `cadquery/cq.py` and `tests/test_cadquery.py`. Source controls accept only official CAD documentation and CadQuery/OCP repository URLs. Downloads have source-count, byte, and time budgets, with checked redirects. Retrieved pages are evidence; embedded setup instructions are never executed.

An investigation includes operation, error, feature graph, minimal geometry, installed versions, required invariants, and budget. Controlled operation terms select relevant references; Scout does not submit private error text or design descriptions to a search service. Lookup and fixed reproduction work without a model.

With a configured provider and a positive `model_budget`, an investigation can also request a source-grounded hypothesis. The budget counts actual provider attempts. By default, the provider receives the operation, installed versions, public source excerpts, and recorded reproduction outcomes. Sending the error, feature graph, geometry, or invariants requires explicit `allow_private_query` authorization. The model may cite only retrieved URLs. Its hypothesis is a separate `sourced` card with `geometry_reproduced: false`; it does not promote an adaptation to reproduced or replace the fixed experiment's card. Live provider reasoning has not been exercised in the documented development environment.

SolutionCards record the source URLs and files, excerpt, proposed mechanism and adaptation, compatible versions, reproduction command and actual outcome, applicability, alternatives, limitations, license notes, hashes, and freshness. States have different meanings:

| State | Meaning |
| --- | --- |
| `sourced` | Relevant indexed evidence; local remedy not yet tested |
| `reproduced` | Fixed disposable experiment succeeded on the listed variants and exact installed versions |
| `rejected` | Reproduction failed, timed out, or was cancelled |
| `stale` | Source snapshot, tested version, or age no longer matches |

The supported experiments cover a 1 mm vertical-edge box fillet, simple selector cardinality, a through-hole Boolean, and single-solid STEP roundtrip. Each runs on 20 × 12 × 8, 24 × 16 × 10, and 30 × 18 × 12 mm boxes. Promotion applies only to those recorded variants. A working fillet on a box does not establish a fillet remedy for a thin-walled enclosure with connector cuts.

Reproduce independently with `python -m shapeloop.scout --reproduce fillet` (also `selector`, `boolean`, or `step`). These commands execute shipped fixed experiments, not downloaded code. The optional watch service refreshes selected references at the configured interval, supports start/stop/cancellation, and yields to foreground investigations. Partial source downloads already cached survive cancellation. Scout never changes an active project, removes a requirement, raises tolerance, or marks geometry accepted.

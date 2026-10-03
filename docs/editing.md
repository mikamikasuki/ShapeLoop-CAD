# Editing and revisions

Parameter changes, feature insertion/removal/updates, constraints, and full validated DesignSpecs use the same domain service from CLI and UI. A candidate records its base revision and branch. Stale submissions are rejected unless the user chooses an explicit alternative branch.

Natural-language editing sends the canonical base DesignSpec and measured context to the configured provider. The validated proposal lists changed parameters, additions, updates, removals, preserved references, new constraints, assumptions, and an explanation. Inspect it before applying. A failed build or required check produces a separate candidate and concrete measured counterexample; the accepted revision remains available.

To add a cutout, insert a `slot` or `pocket` with one input pointing to the current part's terminal feature and a rectangular cutter `size` and `center`. The service updates the part terminal to the new feature. Move it using `update_features` with the existing stable ID. When removing a feature, also repair downstream references and any requirement that explicitly names it; dangling dependencies are rejected.

Supported edge treatments use geometric selectors such as `outer_vertical`, `vertical`, `top_outer`, `bottom_outer`, and `all`. Topology is resolved again on every build. A no-match selector or failing radius reports a kernel/reference error rather than silently treating another edge. Cross-revision face and mesh triangle indices are not stable semantic identifiers.

Accept only a passing candidate. Reject discards it as an alternative without overwriting history. Undo/redo changes the active accepted revision pointer. Branch comparison uses the same world/millimeter frame and reports changed and preserved feature records plus measured reports. Acceptance requires the candidate's full verification result and current artifact integrity regardless of preview or comparison state; Check starts a fresh verification process.

A repair is another explicit bounded candidate: explain the counterexample, consult Scout if useful, change a local operation, rebuild, and remeasure. Scout success is not project acceptance. An unsuccessful bounded search is not a proof that all possible designs are infeasible. Contradictory supported dimensions should expose the fixed component, required envelope, and relevant inequality rather than silently changing one of them.

# Known limitations

- Geometry is limited to the shipped feature vocabulary and supported mechanical families. Freeform surfaces, threads, arbitrary assembly planning, and recovered imported feature history are outside the initial scope.
- Persistent IDs identify semantic features, parts, and datums. Topological predicates and viewport face mappings have limited applicability; mesh triangle IDs and arbitrary face indices are not stable across revisions.
- Exact hole checks cover axis-aligned through-holes. Blind, oblique, threaded, and counterbored holes require additional supported measurements.
- Exact thickness is restricted to named axis-aligned planar probe regions. The application does not certify a global minimum wall thickness.
- Envelope frames support translated XYZ datums. Arbitrarily rotated measurement frames need additional implementation.
- Builds use separate processes and full verification. A validated cache can reuse complete unchanged parts; changed parts rebuild their full graph. Intermediate feature artifacts within a changed part are not reused across revisions.
- Scout uses indexed source lookup and fixed minimal reproductions. Optional provider inference creates a separate sourced hypothesis; it does not execute new remedies, prove an adaptation on an active design, or modify model weights. Live model-assisted Scout reasoning has not been exercised.
- Provider success depends on a compatible user-configured endpoint/model. Mock transport tests establish bounded validation/error behavior, not live CAD reasoning quality.
- Imported STL is stored as a mesh reference. It does not become a checked solid or editable feature tree. Imported STEP source bundles need the reference file for portable rebuilds.
- Orthographic SVG is not a standards-certified drawing. No FEA, material strength, load capacity, real-world fit, printed part, manufacturing trial, or usability study has been established.
- Generator and verifier share one kernel. Validation is dimensional software checking, not independent physical validation.
- macOS ARM64 is the native development host exercised here. Windows/WSL and Linux/container workflows must be exercised on those platforms before being described as tested.
- The tested upstream CAD wheels carry native copyleft notices and a METIS 4.0.3 restriction in CasADi's bundled solver stack. Original code licensing does not certify binary redistribution of that runtime; see the dependency review.

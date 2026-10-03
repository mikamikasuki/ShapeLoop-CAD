# Constraints and measured acceptance

Every requirement is either required or optional. Explicit assumptions and soft objectives are separate records. A required check must return `PASS` before acceptance; both `FAIL` and `UNKNOWN` block it. Model proposals cannot quietly rewrite required constraints. Revise a requirement explicitly in structured editing when its intended value really changes.

Measurements are taken from reopened STEP BREP rather than parameter labels or display meshes:

| Check | Exact supported scope |
| --- | --- |
| BREP | Nonempty valid solids, positive volume, and requested solid count |
| Envelope | OCCT bounds in world or a translated XYZ datum frame |
| Hole / pattern | Axis-aligned through-hole cylindrical surfaces; diameter, axis, count, datum-relative centers and spacing |
| Thickness | One identifiable material interval along a named axis-aligned line probe |
| Keep-out | Actual Boolean common volume against a named box |
| Clearance | Minimum BREP distance between selected parts or a named box |
| Assembly interference | Boolean common volume plus minimum distance in manufacturing placement |
| Internal clearance | Fixed component-box overlap and separation; the component is not shrunk to pass |
| Interchange | STEP reimport, bounds, solid counts and volume consistency |

Reports retain actual and expected quantities, units, tolerances, feature references, method, and explanation. Missing references, ambiguous material intervals, unsupported constraints, and kernel measurement errors produce `UNKNOWN` or `FAIL`. Required unknowns stay visible.

Contact needs explicit meaning: volume below the overlap tolerance does not permit undeclared zero separation. A mating pair may set `allowed_contact=true`; a separated pair also needs the requested clearance. Explicit overlap-volume tolerances use mm³ and distance tolerances use mm. Feature transforms use degrees for angles; angular constraint verification is not part of the initial supported checks.

Units are converted to millimeters internally. Named parameter expressions are dimension-checked. Use `2*mm` for an explicit length and `height/2` for an expression tied to a length parameter. A hole contract should retain its intended baseline coordinates when another feature changes; changing its expected values is a revision to the requirement, not evidence of preservation.

The thickness probe is not a global wall-thickness analysis. No result establishes real-world fit, material strength, FEA, manufacturing tolerance, or printability. Generator and verifier share CadQuery/OCCT, so agreement is software geometry validation using the same kernel.

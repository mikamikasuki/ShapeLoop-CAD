import { describe, expect, it } from "vitest";
import { measurementSummary, measurementTolerances } from "./measurements";
describe("measurement presentation", () => {
  it("keeps linear acceptance tolerance separate from a volumetric overlap threshold", () => {
    expect(
      measurementTolerances(
        {
          expected: { max_overlap_volume: 0.001 },
          tolerances: { length_mm: 0.01, volume_mm3: 0.001 },
        },
        "interference",
      ),
    ).toBe("Length 0.01 mm · max overlap 0.001 mm³");
  });
  it("summarizes actual BREP quantities without reading intended dimensions", () => {
    expect(measurementSummary({ size: [80, 50, 23.75] }, "mm")).toBe(
      "80 × 50 × 23.75 mm",
    );
    expect(
      measurementSummary({
        count: 3,
        diameters: [3, 3, 3],
        axis: "Z",
        centers: [[1, 2, 0]],
      }),
    ).toBe("3 holes · ⌀3 mm · Z axis");
  });
  it("keeps unresolved geometry and forbidden overlap explicit", () => {
    expect(measurementSummary(null)).toBe("No resolved measurement");
    expect(
      measurementSummary({
        overlap_volume: 3.17,
        contained_in_assembly_envelope: false,
      }),
    ).toContain("3.17 mm³ overlap · Outside envelope");
  });
});

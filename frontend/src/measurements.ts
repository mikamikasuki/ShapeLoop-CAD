import { formatValue } from "./api";
export function measurementSummary(actual: any, unit = ""): string {
  if (actual === null || actual === undefined) return "No resolved measurement";
  if (typeof actual === "object" && !Array.isArray(actual)) {
    if (Array.isArray(actual.size))
      return actual.size.map(formatValue).join(" × ") + " " + unit;
    if (actual.count !== undefined && actual.diameters) {
      const values = [
        ...new Set(actual.diameters.map((v: number) => Number(v.toFixed(3)))),
      ];
      return `${actual.count} holes · ⌀${values.map(formatValue).join(" / ")} mm · ${actual.axis} axis`;
    }
    if (actual.thickness !== undefined)
      return `${formatValue(actual.thickness)} mm · ${actual.segments} material interval${actual.segments === 1 ? "" : "s"}`;
    if (actual.overlap_volume !== undefined)
      return (
        `${formatValue(actual.overlap_volume)} mm³ overlap` +
        (actual.distance !== undefined
          ? ` · ${formatValue(actual.distance)} mm separation`
          : "") +
        (actual.contained_in_assembly_envelope !== undefined
          ? ` · ${actual.contained_in_assembly_envelope ? "Contained" : "Outside envelope"}`
          : "")
      );
    if (actual.valid !== undefined)
      return `${actual.valid ? "Valid BREP" : "Invalid BREP"} · ${actual.solids ?? "—"} solid${actual.solids === 1 ? "" : "s"}`;
    if (actual.volume_delta !== undefined)
      return `${actual.solids} solids · ${formatValue(actual.envelope_delta)} mm envelope difference · ${formatValue(actual.volume_delta)} mm³ volume difference`;
    return Object.entries(actual)
      .map(([k, v]) => `${k.replaceAll("_", " ")}: ${formatValue(v)}`)
      .join(" · ");
  }
  if (Array.isArray(actual))
    return actual.map(formatValue).join(" × ") + " " + unit;
  if (typeof actual === "string" && actual.length > 40)
    return actual.slice(0, 12) + "… (file digest)";
  return formatValue(actual) + (unit ? " " + unit : "");
}
export function measurementTolerances(measurement: any, kind: string): string {
  const tolerances = measurement.tolerances || {};
  if (["keepout", "interference", "internal_clearance"].includes(kind)) {
    const volumeLimit =
      measurement.expected?.max_overlap_volume ??
      (kind === "keepout" && typeof measurement.expected === "number"
        ? measurement.expected
        : undefined) ??
      tolerances.volume_mm3;
    const length = tolerances.length_mm ?? measurement.tolerance;
    return `Length ${formatValue(length)} mm · max overlap ${formatValue(volumeLimit)} mm³`;
  }
  if (tolerances.length_mm !== undefined)
    return `${formatValue(tolerances.length_mm)} mm`;
  return `${formatValue(measurement.tolerance)} ${measurement.unit || ""}`;
}

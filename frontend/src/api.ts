import type { Json, Project, Revision } from "./types";
let token = "";
export async function initializeSession() {
  const res = await fetch("/api/session");
  if (!res.ok) throw new Error("The local ShapeLoop-CAD service is unavailable.");
  const data = await res.json();
  token = data.token || data.session_token || "";
  return data;
}
export async function api<T = Json>(
  path: string,
  body?: any,
  method?: string,
): Promise<T> {
  const res = await fetch("/api" + path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: { "Content-Type": "application/json", "X-ShapeLoop-Token": token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let data: any;
  try {
    data = await res.json();
  } catch {
    data = { detail: `HTTP ${res.status}` };
  }
  if (!res.ok) {
    const detail = data.detail || data.error || data.message;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return data as T;
}
export const downloadUrl = (revision: string, file: string) =>
  `/api/artifacts/${encodeURIComponent(revision)}/${encodeURIComponent(file)}`;
export async function uploadReference(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/imports", {
    method: "POST",
    headers: { "X-ShapeLoop-Token": token },
    body,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
export function normalizeProject(data: any): Project {
  const p = data.project || data;
  return {
    ...p,
    revisions: (data.revisions || p.revisions || []).map(normalizeRevision),
    active_revision_id:
      p.active_revision_id ||
      p.active_revision ||
      p.accepted_revision_id ||
      p.current_revision_id,
  };
}
export function normalizeRevision(data: any): Revision {
  const r = data.revision || data;
  return {
    ...r,
    spec: r.spec || r.design_spec || {},
    report: r.report || r.measurements || r.result?.report,
    artifacts: r.artifacts || r.result?.artifacts,
  };
}
export function parameterValue(value: any) {
  return typeof value === "object" ? value.value : value;
}
export function humanize(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
export function formatValue(value: any): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "number")
    return Number(value.toFixed(3)).toLocaleString();
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
export function revisionChecks(revision?: Revision) {
  const report = revision?.report;
  return (
    report?.checks ||
    report?.constraints ||
    (Array.isArray(report?.measurements) ? report.measurements : []) ||
    []
  );
}

export type Json = Record<string, any>;
export interface Parameter {
  value: number | string;
  dimension?: string;
  unit?: string;
  description?: string;
}
export interface Feature {
  id: string;
  name?: string;
  type: string;
  part?: string;
  inputs?: string[];
  parameters?: Json;
  [key: string]: any;
}
export interface Constraint {
  id: string;
  type: string;
  name?: string;
  required?: boolean;
  hard?: boolean;
  parameters?: Json;
  [key: string]: any;
}
export interface DesignSpec {
  units: string;
  name?: string;
  recipe?: string;
  parameters: Record<string, Parameter | number | string>;
  parts: any[];
  features: Feature[];
  constraints: Constraint[];
  [key: string]: any;
}
export interface Check {
  id?: string;
  constraint_id?: string;
  name?: string;
  status: "PASS" | "FAIL" | "UNKNOWN";
  actual?: any;
  measured?: any;
  target?: any;
  unit?: string;
  tolerance?: number;
  method?: string;
  explanation?: string;
  feature_refs?: string[];
  [key: string]: any;
}
export interface Report {
  status?: string;
  passed?: boolean;
  checks?: Check[];
  measurements?: Json;
  parts?: Json;
  [key: string]: any;
}
export interface Revision {
  id: string;
  project_id?: string;
  branch?: string;
  status: string;
  spec: DesignSpec;
  report?: Report;
  artifacts?: Json;
  parent_id?: string;
  created_at?: string;
  error?: any;
  [key: string]: any;
}
export interface Project {
  id: string;
  name: string;
  recipe?: string;
  active_revision_id?: string;
  accepted_revision_id?: string;
  revisions: Revision[];
  [key: string]: any;
}
export interface Job {
  id: string;
  status: string;
  revision_id?: string;
  error?: any;
  [key: string]: any;
}
export interface MeshPart {
  id: string;
  name?: string;
  vertices: number[][] | number[];
  triangles?: number[][] | number[];
  indices?: number[];
  face_ids?: number[];
  face_features?: Record<string, string>;
  triangle_features?: string[];
  [key: string]: any;
}
export interface MeshData {
  parts: MeshPart[];
  bbox?: any;
  tolerance?: number;
  [key: string]: any;
}

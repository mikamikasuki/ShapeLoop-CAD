import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Box,
  Boxes,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  CirclePlus,
  Clock3,
  Code2,
  Cog,
  Copy,
  FileCode2,
  FileJson2,
  FolderOpen,
  GitBranch,
  GitCompareArrows,
  History,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Minus,
  MoreHorizontal,
  PanelLeftClose,
  PanelRightClose,
  Play,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  Undo2,
  Redo2,
  Unlock,
  WifiOff,
  X,
} from "lucide-react";
import {
  api,
  downloadUrl,
  formatValue,
  humanize,
  initializeSession,
  normalizeProject,
  normalizeRevision,
  uploadReference,
  parameterValue,
  revisionChecks,
} from "./api";
import type {
  Constraint,
  Feature,
  Job,
  Json,
  MeshData,
  Project,
  Revision,
} from "./types";
import Viewport from "./Viewport";
import { measurementSummary, measurementTolerances } from "./measurements";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const icons: Record<string, ReactNode> = {
  box: <Box size={14} />,
  cylinder: <CirclePlus size={14} />,
  hole: <CirclePlus size={14} />,
  pocket: <Square size={14} />,
  slot: <Minus size={14} />,
  pattern: <Boxes size={14} />,
  fillet: <Sparkles size={14} />,
  chamfer: <Sparkles size={14} />,
  union: <Layers3 size={14} />,
};
const recipes = [
  {
    id: "enclosure",
    name: "Electronics enclosure",
    description:
      "Separate lid, fixed mounting pattern, and component keep-out.",
    badge: "ASSEMBLY",
    dimensions: "80 × 50 × 30 mm",
  },
  {
    id: "plate",
    name: "Mounting plate",
    description: "Hole pattern, recessed pocket, and chamfered edges.",
    badge: "SINGLE PART",
    dimensions: "100 × 60 × 6 mm",
  },
  {
    id: "bracket",
    name: "Orthogonal bracket",
    description: "Two flanges with a named mounting pattern and edge fillets.",
    badge: "SINGLE PART",
    dimensions: "60 × 40 × 40 mm",
  },
];
function Status({ status }: { status?: string }) {
  const s = status?.toUpperCase() || "PENDING";
  return (
    <span className={`status status-${s.toLowerCase()}`}>
      {s === "PASS" ||
      s === "ACCEPTED" ||
      s === "COMPLETED" ||
      s === "SUCCEEDED" ? (
        <Check size={11} />
      ) : s === "FAIL" || s === "FAILED" ? (
        <X size={11} />
      ) : (
        <Clock3 size={11} />
      )}{" "}
      {s.replaceAll("_", " ")}
    </span>
  );
}
function Modal({
  title,
  subtitle,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    const fn = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog?.addEventListener("cancel", fn);
    return () => {
      dialog?.removeEventListener("cancel", fn);
      dialog?.close();
    };
  }, [onClose]);
  return (
    <dialog ref={ref} className={`modal ${wide ? "modal-wide" : ""}`}>
      <div className="modal-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={19} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function ErrorMessage({ error, clear }: { error: string; clear?: () => void }) {
  return (
    <div role="alert" className="error-message">
      <CircleHelp size={16} />
      <span>{error}</span>
      {clear && (
        <button onClick={clear} aria-label="Dismiss error">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project>(),
    [selectedRevision, setSelectedRevision] = useState(""),
    [selectedFeature, setSelectedFeature] = useState(""),
    [selectedFace, setSelectedFace] = useState<{
      part: string;
      face?: string | number;
    }>(),
    [mesh, setMesh] = useState<MeshData>(),
    [meshRevision, setMeshRevision] = useState(""),
    [compareMesh, setCompareMesh] = useState<MeshData>();
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [connecting, setConnecting] = useState(true),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job>(),
    [hidden, setHidden] = useState(new Set<string>());
  const [dialog, setDialog] = useState<
      | "library"
      | "export"
      | "settings"
      | "scout"
      | "feature"
      | "constraint"
      | "help"
      | "import"
      | "reference"
      | null
    >(null),
    [inspectorTab, setInspectorTab] = useState("parameters"),
    [bottomTab, setBottomTab] = useState("intent"),
    [query, setQuery] = useState(""),
    [leftOpen, setLeftOpen] = useState(() => window.innerWidth > 700),
    [rightOpen, setRightOpen] = useState(() => window.innerWidth > 700);
  const [draft, setDraft] = useState<Record<string, string>>({}),
    [units, setUnits] = useState("mm"),
    [instruction, setInstruction] = useState(""),
    [proposal, setProposal] = useState<Json>(),
    [provider, setProvider] = useState<Json>({}),
    [branch, setBranch] = useState("main"),
    [compareFrom, setCompareFrom] = useState(""),
    [comparison, setComparison] = useState<Json>();
  const [references, setReferences] = useState<Json[]>([]),
    [selectedReference, setSelectedReference] = useState<Json>(),
    [failedPreview, setFailedPreview] = useState(false),
    [leftWidth, setLeftWidth] = useState(238),
    [rightWidth, setRightWidth] = useState(308);
  const projectId = useRef("");
  const selectedId = useRef("");
  const jobPoll = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const revision =
    project?.revisions.find((r) => r.id === selectedRevision) ||
    project?.revisions.at(-1);
  const accepted = project?.revisions.find(
    (r) => r.id === project.active_revision_id,
  );
  const visibleRevision =
    failedPreview ||
    (!accepted && revision?.status === "failed") ||
    [
      "accepted",
      "candidate",
      "validated",
      "built",
      "completed",
      "passed",
    ].includes(revision?.status || "")
      ? revision
      : accepted;
  const features = revision?.spec.features || [],
    parts = revision?.spec.parts || [],
    constraints = revision?.spec.constraints || [],
    checks = revisionChecks(revision);
  const passed = checks.filter((c: any) => c.status === "PASS").length,
    failed = checks.filter((c: any) => c.status === "FAIL").length,
    unknown = checks.filter((c: any) => c.status === "UNKNOWN").length;
  const activeFeature = features.find((f) => f.id === selectedFeature);
  const dirty =
    Object.entries(draft).some(
      ([name, value]) =>
        value !== String(parameterValue(revision?.spec.parameters[name])),
    ) || units !== (revision?.spec.units || "mm");
  useEffect(() => {
    projectId.current = project?.id || "";
  }, [project]);
  useEffect(() => {
    selectedId.current = selectedRevision;
  }, [selectedRevision]);
  const loadReferences = useCallback(async () => {
    try {
      const list = await api<any>("/references");
      setReferences(Array.isArray(list) ? list : list.references || []);
    } catch {}
  }, []);
  const loadProjects = useCallback(async () => {
    const data = await api<any>("/projects");
    const result = (Array.isArray(data) ? data : data.projects || []).map(
      normalizeProject,
    );
    setProjects(result);
    return result;
  }, []);
  const loadProject = useCallback(async (id: string, select?: string) => {
    const p = normalizeProject(await api("/projects/" + id));
    setProject(p);
    localStorage.setItem("shapeloop.current-project", p.id);
    if (select) setSelectedRevision(select);
    else if (!p.revisions.some((r) => r.id === selectedId.current))
      setSelectedRevision(p.active_revision_id || p.revisions.at(-1)?.id || "");
    return p;
  }, []);
  const refreshSettings = useCallback(async () => {
    try {
      setProvider(await api("/settings"));
    } catch {}
  }, []);
  useEffect(() => {
    let active = true;
    initializeSession()
      .then(async () => {
        await refreshSettings();
        await loadReferences();
        const list = await loadProjects();
        if (active && list.length) {
          const p = await loadProject(
            (
              list.find(
                (p: Project) =>
                  p.id === localStorage.getItem("shapeloop.current-project"),
              ) || list[0]
            ).id,
          );
          const pending = p.revisions.find((r) => r.status === "building");
          if (pending?.job_id)
            watchJob(await api<Job>("/jobs/" + pending.job_id));
        } else if (active) setDialog("library");
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setConnecting(false);
      });
    return () => {
      active = false;
      clearTimeout(jobPoll.current);
    };
  }, [loadProjects, loadProject, refreshSettings, loadReferences]);
  useEffect(() => {
    if (!revision) return;
    setFailedPreview(false);
    setDraft(
      Object.fromEntries(
        Object.entries(revision.spec.parameters || {}).map(([k, v]) => [
          k,
          String(parameterValue(v)),
        ]),
      ),
    );
    setUnits(revision.spec.units || "mm");
    setBranch(revision.branch || "main");
    setHidden(new Set());
  }, [revision?.id]);
  useEffect(() => {
    let current = true;
    if (!visibleRevision) {
      setMesh(undefined);
      return;
    }
    fetch(downloadUrl(visibleRevision.id, "mesh.json"))
      .then((r) => {
        if (!r.ok) throw new Error("Tessellation is not available yet.");
        return r.json();
      })
      .then((data) => {
        if (current) {
          setMesh(data);
          setMeshRevision(visibleRevision.id);
        }
      })
      .catch(() => {
        if (current) {
          if (!accepted) setMesh(undefined);
          setNotice(
            "Preview could not load; the displayed geometry is from the previous revision.",
          );
        }
      });
    return () => {
      current = false;
    };
  }, [visibleRevision?.id, visibleRevision?.status, accepted?.id]);
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSelectedFeature("");
        setSelectedFace(undefined);
      }
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key === "z" &&
        !(
          e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLTextAreaElement
        )
      ) {
        e.preventDefault();
        navigateHistory(e.shiftKey ? "redo" : "undo");
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [project?.id]);
  async function run<T>(action: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function watchJob(next: Job) {
    setJob(next);
    clearTimeout(jobPoll.current);
    async function poll() {
      try {
        const j = await api<Job>("/jobs/" + next.id);
        setJob(j);
        if (projectId.current) await loadProject(projectId.current);
        if (
          [
            "queued",
            "running",
            "pending",
            "building",
            "verifying",
            "cancelling",
          ].includes(j.status)
        ) {
          jobPoll.current = setTimeout(poll, 1000);
        } else {
          await loadProjects();
          if (j.status === "failed") {
            setNotice(
              "Candidate failed. Your accepted geometry remains available.",
            );
          } else if (j.status === "cancelled") {
            setNotice(
              "Build cancelled. The previous accepted revision is preserved.",
            );
          } else
            setNotice(
              "Geometry built and independently measured from the exported STEP.",
            );
        }
      } catch (e: any) {
        setError(e.message);
      }
    }
    jobPoll.current = setTimeout(poll, 500);
  }
  async function createProject(name: string, recipe: string) {
    await run(async () => {
      const data = await api<any>("/projects", { name, recipe });
      const p = normalizeProject(data);
      await loadProjects();
      setProject(p);
      projectId.current = p.id;
      const rid =
        data.revision?.id || p.revisions.at(-1)?.id || p.active_revision_id;
      setSelectedRevision(rid || "");
      setDialog(null);
      setNotice("Starting recipe created. Geometry is being built.");
      if (data.job) watchJob(data.job);
      else if (rid) {
        const rev = p.revisions.find((r) => r.id === rid);
        if (
          !["accepted", "validated", "built", "passed", "completed"].includes(
            rev?.status || "",
          )
        )
          watchJob(await api<Job>("/revisions/" + rid + "/build"));
      }
      await loadProject(p.id, rid);
    });
  }
  async function edit(payload: Json) {
    if (!project || !revision) return;
    await run(async () => {
      const result = await api<any>("/projects/" + project.id + "/edit", {
        base_revision: revision.id,
        branch,
        ...payload,
      });
      const next = normalizeRevision(result.revision || result);
      setProposal(undefined);
      await loadProject(project.id, next.id);
      setBottomTab("intent");
      if (result.job) watchJob(result.job);
      setNotice("Candidate created. Accept it after the required checks pass.");
      setDialog(null);
    });
  }
  async function removeFeature(feature: Feature) {
    if (!revision) return;
    const replacement = feature.inputs?.[0];
    const spec = {
      ...revision.spec,
      features: revision.spec.features
        .filter((f) => f.id !== feature.id)
        .map((f) => ({
          ...f,
          inputs: f.inputs?.flatMap((id) =>
            id === feature.id ? (replacement ? [replacement] : []) : [id],
          ),
        })),
      parts: revision.spec.parts.map((p) =>
        p.feature === feature.id ? { ...p, feature: replacement } : p,
      ),
    };
    await edit({ spec });
  }
  async function generateProject(name: string, instruction: string) {
    await run(async () => {
      const data = await api<any>("/generate", { name, instruction });
      await loadProjects();
      const p = normalizeProject(data);
      setProject(p);
      projectId.current = p.id;
      setSelectedRevision(data.revision.id);
      setDialog(null);
      watchJob(data.job);
      await loadProject(p.id, data.revision.id);
    });
  }
  async function importFile(file: File) {
    await run(async () => {
      const data = await uploadReference(file);
      if (data.project) {
        await loadProjects();
        projectId.current = data.project.id;
        await loadProject(data.project.id, data.revision.id);
        watchJob(data.job);
        setDialog(null);
      } else {
        await loadReferences();
        setNotice(data.note || "Reference mesh imported.");
        setDialog(null);
      }
    });
  }
  function resizePanel(side: "left" | "right", event: React.PointerEvent) {
    event.preventDefault();
    const start = event.clientX,
      initial = side === "left" ? leftWidth : rightWidth;
    function move(e: PointerEvent) {
      const value = Math.max(
        side === "left" ? 170 : 230,
        Math.min(
          side === "left" ? 380 : 450,
          initial + (e.clientX - start) * (side === "left" ? 1 : -1),
        ),
      );
      side === "left" ? setLeftWidth(value) : setRightWidth(value);
    }
    function stop() {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }
  async function applyParameters() {
    const parameters: Json = {};
    for (const [name, value] of Object.entries(draft))
      if (value !== String(parameterValue(revision?.spec.parameters[name])))
        parameters[name] =
          value.trim() !== "" && Number.isFinite(Number(value))
            ? Number(value)
            : value;
    await edit({
      parameters,
      ...(units !== revision?.spec.units ? { units } : {}),
    });
  }
  async function acceptRevision() {
    if (!revision || !project) return;
    await run(async () => {
      await api("/revisions/" + revision.id + "/accept", {});
      await loadProject(project.id, revision.id);
      await loadProjects();
      setNotice("Revision accepted. All required supported checks passed.");
    });
  }
  async function rejectRevision() {
    if (!revision || !project) return;
    await run(async () => {
      await api("/revisions/" + revision.id + "/reject", {});
      await loadProject(project.id, project.active_revision_id);
      setNotice("Candidate rejected.");
    });
  }
  async function navigateHistory(direction: "undo" | "redo") {
    if (!projectId.current) return;
    await run(async () => {
      const p = normalizeProject(
        await api("/projects/" + projectId.current + "/" + direction, {}),
      );
      setProject(p);
      setSelectedRevision(p.active_revision_id || "");
      setNotice(
        direction === "undo"
          ? "Previous accepted revision restored."
          : "Next accepted revision restored.",
      );
    });
  }
  async function propose() {
    if (!project || !revision || !instruction.trim()) return;
    await run(async () => {
      setProposal(
        await api("/projects/" + project.id + "/propose", {
          base_revision: revision.id,
          instruction,
        }),
      );
      setNotice("Review the structured proposal before applying it.");
    });
  }
  async function applyProposal() {
    if (!project || !proposal) return;
    await run(async () => {
      const result = await api<any>(
        "/projects/" + project.id + "/apply-proposal",
        proposal,
      );
      await loadProject(project.id, result.revision.id);
      if (result.job) watchJob(result.job);
      setProposal(undefined);
    });
  }
  async function compare(id: string) {
    if (!project || !revision) return;
    setCompareFrom(id);
    if (!id) {
      setCompareMesh(undefined);
      setComparison(undefined);
      return;
    }
    await run(async () => {
      setComparison(
        await api(
          `/projects/${project.id}/compare?from=${encodeURIComponent(id)}&to=${encodeURIComponent(revision.id)}`,
        ),
      );
      const m = await fetch(downloadUrl(id, "mesh.json"));
      if (m.ok) setCompareMesh(await m.json());
    });
  }
  function toggleVisibility(id: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  const jobRunning =
    job &&
    [
      "queued",
      "pending",
      "running",
      "building",
      "verifying",
      "cancelling",
    ].includes(job.status);
  const canAccept =
    revision &&
    revision.id !== project?.active_revision_id &&
    [
      "validated",
      "built",
      "passed",
      "completed",
      "candidate",
      "ready",
    ].includes(revision.status) &&
    !failed &&
    !unknown &&
    checks.length > 0;
  const configured =
    !!(provider.provider?.model || provider.model) &&
    !!(provider.provider?.endpoint || provider.endpoint);
  return (
    <div
      className={`app ${leftOpen ? "" : "left-collapsed"} ${rightOpen ? "" : "right-collapsed"}`}
    >
      <header className="topbar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setDialog("library");
          }}
          aria-label="ShapeLoop-CAD project library"
        >
          <span className="brand-mark">
            <span />
            <span />
          </span>
          ShapeLoop-CAD<span className="alpha-tag">LOCAL</span>
        </a>
        <div className="top-divider" />
        <button className="project-title" onClick={() => setDialog("library")}>
          <FolderOpen size={15} />
          {project?.name || "Untitled workspace"}
          <ChevronDown size={13} />
        </button>
        <span className="saved-indicator">
          <span className="live-dot" />
          {project ? "Saved locally" : "Local-first CAD"}
        </span>
        <div className="topbar-right">
          <button className="quiet-button" onClick={() => setDialog("scout")}>
            <Search size={15} />
            SolutionScout
          </button>
          <button
            className="icon-button"
            aria-label="Settings"
            title="Settings"
            onClick={() => setDialog("settings")}
          >
            <Cog size={17} />
          </button>
          <button
            className="export-button"
            onClick={() => setDialog("export")}
            disabled={!visibleRevision}
          >
            <ArrowDownToLine size={15} /> Export <ChevronDown size={12} />
          </button>
        </div>
      </header>
      <div className="workspace-toolbar">
        <div className="workspace-tabs">
          <button
            className="selected"
            onClick={() => {
              setBottomTab("intent");
              setInspectorTab("parameters");
            }}
          >
            <Box size={14} /> Design
          </button>
          <button
            onClick={() => {
              setBottomTab("revisions");
            }}
            className={bottomTab === "revisions" ? "selected" : ""}
          >
            <GitBranch size={14} /> Revisions
          </button>
          <button onClick={() => setDialog("scout")}>
            <Code2 size={14} /> Knowledge
          </button>
        </div>
        <div className="toolbar-actions">
          <button
            className="icon-button"
            title="Undo accepted revision"
            aria-label="Undo"
            disabled={!project || busy}
            onClick={() => navigateHistory("undo")}
          >
            <Undo2 size={15} />
          </button>
          <button
            className="icon-button"
            title="Redo accepted revision"
            aria-label="Redo"
            disabled={!project || busy}
            onClick={() => navigateHistory("redo")}
          >
            <Redo2 size={15} />
          </button>
          <div className="top-divider" />
          <span className="branch-label">
            <GitBranch size={13} />
            {revision?.branch || "main"}
          </span>
          <span className="revision-label">
            {revision
              ? "r" +
                (project!.revisions.findIndex((r) => r.id === revision.id) + 1)
                  .toString()
                  .padStart(2, "0")
              : "—"}
          </span>
          <button
            className="icon-button"
            aria-label="Workbench guide"
            onClick={() => setDialog("help")}
          >
            <CircleHelp size={16} />
          </button>
        </div>
      </div>
      <main
        className="workbench"
        style={{
          gridTemplateColumns: `${leftOpen ? leftWidth + "px " : ""}minmax(260px,1fr)${rightOpen ? " " + rightWidth + "px" : ""}`,
        }}
      >
        {leftOpen && (
          <aside className="sidebar">
            <div
              className="panel-resizer resizer-left"
              role="separator"
              aria-label="Resize design tree"
              aria-orientation="vertical"
              tabIndex={0}
              onPointerDown={(e) => resizePanel("left", e)}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft")
                  setLeftWidth(Math.max(170, leftWidth - 10));
                if (e.key === "ArrowRight")
                  setLeftWidth(Math.min(380, leftWidth + 10));
              }}
            />
            <div className="panel-header">
              <span>Design tree</span>
              <div>
                <button
                  className="icon-button"
                  aria-label="New feature"
                  title="Insert feature"
                  disabled={!revision}
                  onClick={() => setDialog("feature")}
                >
                  <Plus size={16} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Collapse design tree"
                  onClick={() => setLeftOpen(false)}
                >
                  <PanelLeftClose size={15} />
                </button>
              </div>
            </div>
            <label className="tree-search">
              <Search size={13} />
              <input
                aria-label="Search features"
                placeholder="Find a feature…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <kbd>/</kbd>
            </label>
            <div className="tree-content">
              <div className="tree-root">
                <ChevronDown size={13} />
                <Box size={15} />
                <b>{revision?.spec.name || "Design assembly"}</b>
                <span>{parts.length}</span>
              </div>
              {parts.map((part) => (
                <div key={part.id} className="part-group">
                  <div className="part-row">
                    <ChevronDown size={12} />
                    <button
                      className="part-label"
                      onClick={() => {
                        setSelectedFeature(part.id);
                        setSelectedFace({ part: part.id });
                      }}
                    >
                      <Box size={14} />
                      {part.name || humanize(part.id)}
                    </button>
                    <button
                      className={`visibility-button ${hidden.has(part.id) ? "hidden-part" : ""}`}
                      aria-label={`${hidden.has(part.id) ? "Show" : "Hide"} ${part.name || part.id}`}
                      title="Toggle part visibility"
                      onClick={() => toggleVisibility(part.id)}
                    >
                      {hidden.has(part.id) ? (
                        <Unlock size={12} />
                      ) : (
                        <Check size={12} />
                      )}
                    </button>
                  </div>
                  {features
                    .filter(
                      (f) =>
                        f.part === part.id &&
                        (!query ||
                          `${f.id} ${f.name} ${f.type}`
                            .toLowerCase()
                            .includes(query.toLowerCase())),
                    )
                    .map((f) => (
                      <button
                        key={f.id}
                        className={`feature-row ${selectedFeature === f.id ? "feature-selected" : ""}`}
                        onClick={() => {
                          setSelectedFeature(f.id);
                          setInspectorTab("parameters");
                        }}
                      >
                        <span className="feature-line" />
                        {icons[f.type] || <Layers3 size={14} />}
                        <span>{f.name || humanize(f.id)}</span>
                        <span className="feature-type">{f.type}</span>
                      </button>
                    ))}
                </div>
              ))}
              {!parts.length && (
                <p className="tree-empty">
                  Create a project to see parts and their dependencies.
                </p>
              )}
              <div className="tree-section-label">
                REFERENCE GEOMETRY{" "}
                <button
                  aria-label="Import reference geometry"
                  title="Import STEP or STL reference"
                  onClick={() => setDialog("import")}
                >
                  <Plus size={12} />
                </button>
              </div>
              {references.map((reference) => (
                <button
                  className="reference-row"
                  key={reference.id}
                  onClick={() => {
                    setSelectedReference(reference);
                    setDialog("reference");
                  }}
                >
                  <Boxes size={13} />
                  <span>{reference.name}</span>
                  <span>STL</span>
                </button>
              ))}
              <div className="datum-row">
                <AxisGlyph />
                Origin datum <span>XYZ</span>
              </div>
              <div className="datum-row">
                <GridGlyph />
                XY plane <span>Z = 0</span>
              </div>
            </div>
            <div className="sidebar-footer">
              <div className="section-eyebrow">PROJECT LIBRARY</div>
              <button
                className="library-button"
                onClick={() => setDialog("library")}
              >
                <FolderOpen size={17} />
                <div>
                  <b>My designs</b>
                  <span>
                    {projects.length} saved project
                    {projects.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <ArrowUpRight size={14} />
              </button>
            </div>
          </aside>
        )}
        <div className="center-column">
          <div className="viewport-wrap">
            {!leftOpen && (
              <button
                className="restore-panel left"
                aria-label="Expand design tree"
                onClick={() => setLeftOpen(true)}
              >
                <ArrowRight size={14} />
              </button>
            )}
            {!rightOpen && (
              <button
                className="restore-panel right"
                aria-label="Expand inspector"
                onClick={() => setRightOpen(true)}
              >
                <ArrowLeft size={14} />
              </button>
            )}
            <Viewport
              data={mesh}
              compare={compareMesh}
              hidden={hidden}
              selected={selectedFeature}
              onSelect={(id, part, face) => {
                setSelectedFeature(id);
                setSelectedFace({ part, face });
              }}
              onMeasure={(entities, kind) =>
                api("/revisions/" + visibleRevision?.id + "/measure", {
                  entities,
                  kind,
                })
              }
              loading={!!jobRunning || connecting}
              revisionLabel={
                failedPreview && meshRevision === revision?.id
                  ? "Failed candidate preview"
                  : meshRevision && meshRevision === revision?.id
                    ? "Current revision"
                    : meshRevision
                      ? "Last accepted revision"
                      : "No active geometry"
              }
            />
            {jobRunning && (
              <div className="build-overlay">
                <LoaderCircle size={15} className="spinning" />
                <span>
                  Building candidate <b>{job.status}</b>
                </span>
                <button
                  onClick={() =>
                    run(async () => {
                      const j = await api<Job>(
                        "/jobs/" + job.id + "/cancel",
                        {},
                      );
                      setJob(j);
                    })
                  }
                >
                  Cancel
                </button>
              </div>
            )}
            {comparison && (
              <div className="compare-badge">
                <GitCompareArrows size={13} />
                Overlay comparison <span>previous</span>
                <button
                  aria-label="Close comparison"
                  onClick={() => {
                    setCompareMesh(undefined);
                    setComparison(undefined);
                    setCompareFrom("");
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            )}
          </div>
          <section className="intent-panel">
            <div className="intent-header">
              <div className="bottom-tabs">
                <button
                  className={bottomTab === "intent" ? "active" : ""}
                  onClick={() => setBottomTab("intent")}
                >
                  <Sparkles size={14} />
                  Intent
                </button>
                <button
                  className={bottomTab === "revisions" ? "active" : ""}
                  onClick={() => setBottomTab("revisions")}
                >
                  <History size={14} />
                  Revision history<span>{project?.revisions.length || 0}</span>
                </button>
                <button
                  className={bottomTab === "results" ? "active" : ""}
                  onClick={() => setBottomTab("results")}
                >
                  <ShieldCheck size={14} />
                  Build report
                </button>
              </div>
              <span className="provider-chip">
                <span className={configured ? "live-dot" : "offline-dot"} />
                {configured
                  ? provider.provider?.model || provider.model
                  : "Manual mode"}
              </span>
            </div>
            {bottomTab === "intent" && (
              <div className="intent-body">
                {proposal ? (
                  <div className="proposal-review">
                    <div>
                      <b>Proposed edit</b>
                      <span>
                        {Object.entries(proposal.parameters || {})
                          .map(
                            ([key, value]) =>
                              `${humanize(key)} → ${formatValue(value)}`,
                          )
                          .join(" · ") || "Feature and constraint changes"}
                      </span>
                      {proposal.assumptions?.map((a: string) => (
                        <small key={a}>{a}</small>
                      ))}
                      <details className="proposal-details">
                        <summary>Review complete structured proposal</summary>
                        <pre>{JSON.stringify(proposal, null, 2)}</pre>
                      </details>
                    </div>
                    <button
                      className="quiet-button"
                      onClick={() => setProposal(undefined)}
                    >
                      Dismiss
                    </button>
                    <button
                      className="primary-button"
                      disabled={busy}
                      onClick={applyProposal}
                    >
                      Build proposal <ArrowRight size={14} />
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="intent-input">
                      <Sparkles size={18} />
                      <textarea
                        aria-label="Design instruction"
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder={
                          configured
                            ? "Describe your change. ShapeLoop-CAD will propose edits and preserve your requirements."
                            : "Configure a model to propose edits in English or Chinese. Manual editing is ready."
                        }
                      />
                      <button
                        aria-label="Propose natural-language edit"
                        className="send-button"
                        onClick={propose}
                        disabled={
                          busy ||
                          !configured ||
                          !instruction.trim() ||
                          !revision
                        }
                      >
                        <ArrowRight size={18} />
                      </button>
                    </label>
                    <div className="intent-footnote">
                      <span>
                        <ShieldCheck size={12} /> Changes are built as
                        candidates before acceptance.
                      </span>
                      {!configured && (
                        <button onClick={() => setDialog("settings")}>
                          Connect a provider <ArrowUpRight size={12} />
                        </button>
                      )}
                    </div>
                  </>
                )}
                {notice && (
                  <div role="status" className="notice">
                    <Check size={12} />
                    {notice}
                  </div>
                )}
              </div>
            )}
            {bottomTab === "revisions" && (
              <div className="history-body">
                {project?.revisions.map((r, i) => (
                  <button
                    key={r.id}
                    className={`revision-card ${r.id === revision?.id ? "active" : ""}`}
                    onClick={() => {
                      setSelectedRevision(r.id);
                      setCompareMesh(undefined);
                      setComparison(undefined);
                      setCompareFrom("");
                    }}
                  >
                    <div>
                      <GitBranch size={14} />
                      <b>r{String(i + 1).padStart(2, "0")}</b>
                      <span>{r.branch || "main"}</span>
                    </div>
                    <Status status={r.status} />
                    <small>
                      {r.created_at
                        ? new Date(r.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : r.id.slice(0, 8)}
                    </small>
                  </button>
                ))}
                {!project && <p className="muted">No revisions yet.</p>}
              </div>
            )}
            {bottomTab === "results" && (
              <div className="report-body">
                {revision?.status === "failed" && accepted && (
                  <button
                    className="failed-preview-button quiet-button"
                    onClick={() => setFailedPreview(!failedPreview)}
                  >
                    {failedPreview
                      ? "Return to accepted geometry"
                      : "Preview failed candidate geometry"}
                  </button>
                )}
                <div className="report-summary">
                  <ShieldCheck size={22} />
                  <div>
                    <b>
                      {failed
                        ? "Candidate failed verification"
                        : unknown
                          ? "Unresolved measurements"
                          : passed
                            ? "Geometry checks passed"
                            : "No build report yet"}
                    </b>
                    <span>
                      {passed} passed · {failed} failed · {unknown} unknown
                    </span>
                  </div>
                  {job && !jobRunning && job.status === "failed" && (
                    <button
                      className="quiet-button"
                      onClick={() =>
                        run(async () => {
                          watchJob(
                            await api<Job>("/jobs/" + job.id + "/retry", {}),
                          );
                        })
                      }
                    >
                      Retry build
                    </button>
                  )}
                </div>
                <p>
                  {revision?.error
                    ? formatValue(revision.error)
                    : revision?.report?.explanation ||
                      "BREP and reopened STEP checks use the same geometry kernel. They do not certify strength or physical fit."}
                </p>
                {revision?.report?.conflicts?.map(
                  (conflict: any, i: number) => (
                    <div className="conflict-proof" key={i}>
                      <b>{conflict.explanation}</b>
                      <code>{conflict.inequality}</code>
                      <span>{conflict.choices?.join(" · ")}</span>
                    </div>
                  ),
                )}
                <div className="report-links">
                  <button
                    className="text-button"
                    onClick={() => setInspectorTab("constraints")}
                  >
                    Inspect measured requirements <ArrowRight size={13} />
                  </button>
                  {revision?.status === "failed" && (
                    <button
                      className="text-button"
                      onClick={() => setDialog("scout")}
                    >
                      Investigate with Scout <Search size={13} />
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
        {rightOpen && (
          <aside className="inspector">
            <div
              className="panel-resizer resizer-right"
              role="separator"
              aria-label="Resize inspector"
              aria-orientation="vertical"
              tabIndex={0}
              onPointerDown={(e) => resizePanel("right", e)}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft")
                  setRightWidth(Math.min(450, rightWidth + 10));
                if (e.key === "ArrowRight")
                  setRightWidth(Math.max(230, rightWidth - 10));
              }}
            />
            <div className="panel-header">
              <span>Inspector</span>
              <div>
                <Settings2 size={14} />
                <button
                  className="icon-button"
                  aria-label="Collapse inspector"
                  onClick={() => setRightOpen(false)}
                >
                  <PanelRightClose size={15} />
                </button>
              </div>
            </div>
            <div className="inspector-tabs">
              <button
                className={inspectorTab === "parameters" ? "active" : ""}
                onClick={() => setInspectorTab("parameters")}
              >
                Parameters
              </button>
              <button
                className={inspectorTab === "constraints" ? "active" : ""}
                onClick={() => setInspectorTab("constraints")}
              >
                Requirements <span>{constraints.length}</span>
              </button>
            </div>
            <div className="inspector-scroll">
              {inspectorTab === "parameters" ? (
                <>
                  <div className="selection-info">
                    <div className="selection-icon">
                      {activeFeature ? (
                        icons[activeFeature.type] || <Box size={19} />
                      ) : (
                        <Boxes size={19} />
                      )}
                    </div>
                    <div>
                      <h3>
                        {activeFeature?.name ||
                          activeFeature?.id ||
                          revision?.spec.name ||
                          "No design selected"}
                      </h3>
                      <span>
                        {activeFeature
                          ? activeFeature.type + " · " + activeFeature.id
                          : `${parts.length} part${parts.length !== 1 ? "s" : ""} · ${features.length} features`}
                      </span>
                    </div>
                  </div>
                  {selectedFace?.face !== undefined && (
                    <div className="selection-face">
                      Selected BREP face{" "}
                      <code>{String(selectedFace.face)}</code>
                      <span>Revision-local mapping</span>
                    </div>
                  )}
                  {activeFeature && (
                    <FeatureDetails
                      feature={activeFeature}
                      features={features}
                      onUpdate={(parameters) =>
                        edit({
                          update_features: [
                            { id: activeFeature.id, parameters },
                          ],
                        })
                      }
                      onRemove={() => removeFeature(activeFeature)}
                      busy={busy}
                    />
                  )}
                  <div className="inspector-section-header">
                    <h4>Design dimensions</h4>
                    <label>
                      <span className="sr-only">Display units</span>
                      <select
                        aria-label="Design units"
                        value={units}
                        onChange={(e) => setUnits(e.target.value)}
                        disabled={!revision}
                      >
                        <option value="mm">mm</option>
                        <option value="cm">cm</option>
                        <option value="in">in</option>
                      </select>
                    </label>
                  </div>
                  <div className="parameter-list">
                    {Object.entries(revision?.spec.parameters || {}).map(
                      ([name, value]) => (
                        <label key={name} className="parameter-row">
                          <span>{humanize(name)}</span>
                          <div>
                            <input
                              aria-label={humanize(name)}
                              value={draft[name] ?? ""}
                              onChange={(e) =>
                                setDraft({ ...draft, [name]: e.target.value })
                              }
                              inputMode="decimal"
                            />
                            <span>
                              {typeof value === "object" &&
                              value.dimension !== "length"
                                ? value.dimension === "angle"
                                  ? "°"
                                  : "—"
                                : typeof value === "object" && value.unit
                                  ? value.unit
                                  : units}
                            </span>
                          </div>
                        </label>
                      ),
                    )}
                  </div>
                  {revision && (
                    <button
                      className="apply-button"
                      onClick={applyParameters}
                      disabled={!dirty || busy || !!jobRunning}
                    >
                      {busy ? (
                        <LoaderCircle size={14} className="spinning" />
                      ) : (
                        <Play size={13} />
                      )}
                      Build changes {dirty && <span>Candidate</span>}
                    </button>
                  )}
                  <div className="inspector-divider" />
                  <div className="inspector-section-header">
                    <h4>Preservation checks</h4>
                    <span>
                      {passed}/{checks.length}
                    </span>
                  </div>
                  <div className="mini-checks">
                    {checks.slice(0, 4).map((c: any, i: number) => (
                      <button
                        key={c.id || i}
                        onClick={() => setInspectorTab("constraints")}
                      >
                        <span
                          className={`check-icon ${c.status.toLowerCase()}`}
                        >
                          {c.status === "PASS" ? (
                            <Check size={12} />
                          ) : c.status === "FAIL" ? (
                            <X size={12} />
                          ) : (
                            <CircleHelp size={12} />
                          )}
                        </span>
                        {c.name ||
                          humanize(c.constraint_id || c.id || "Requirement")}
                        <LockKeyhole size={11} />
                      </button>
                    ))}
                    {!checks.length && (
                      <p className="muted">
                        Measurements appear after the first build.
                      </p>
                    )}
                  </div>
                  {revision?.spec.assumptions?.length > 0 && (
                    <div className="assumptions">
                      <span className="section-eyebrow">
                        DESIGN ASSUMPTIONS
                      </span>
                      {revision?.spec.assumptions?.map((a: string) => (
                        <p key={a}>{a}</p>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="requirements-heading">
                    <div>
                      <ShieldCheck size={18} />
                      <h3>Required geometry</h3>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Add requirement"
                      onClick={() => setDialog("constraint")}
                      disabled={!revision}
                    >
                      <Plus size={15} />
                    </button>
                  </div>
                  <p className="requirements-intro">
                    Checks measure the resulting BREP and reopened STEP. Unknown
                    checks remain unresolved.
                  </p>
                  {constraints.map((c: Constraint) => (
                    <RequirementCard
                      key={c.id}
                      constraint={c}
                      measurement={checks.find(
                        (result: any) =>
                          (result.constraint_id || result.id) === c.id,
                      )}
                      busy={busy}
                      onUpdate={(updated) =>
                        edit({
                          constraints: constraints.map((item) =>
                            item.id === c.id ? updated : item,
                          ),
                        })
                      }
                      onSelect={() => {
                        setSelectedFeature(c.features?.[0] || "");
                        setInspectorTab("parameters");
                      }}
                    />
                  ))}
                  {!constraints.length && (
                    <p className="muted">
                      Add explicit requirements to this design.
                    </p>
                  )}
                </>
              )}
            </div>
            {revision && (
              <div className="acceptance-footer">
                <div>
                  <span className="live-dot" />
                  {revision.id === project?.active_revision_id
                    ? "Accepted revision"
                    : failed
                      ? "Failed candidate"
                      : jobRunning
                        ? "Candidate building"
                        : "Candidate revision"}
                  <Status status={revision.status} />
                </div>
                {revision.id !== project?.active_revision_id && (
                  <div className="acceptance-actions">
                    <button
                      className="quiet-button"
                      onClick={rejectRevision}
                      disabled={busy || !!jobRunning}
                    >
                      Reject
                    </button>
                    <button
                      className="primary-button"
                      onClick={acceptRevision}
                      disabled={busy || !canAccept}
                    >
                      <CheckCheck size={14} />
                      Accept revision
                    </button>
                  </div>
                )}
                <label className="branch-input">
                  <GitBranch size={12} />
                  <input
                    aria-label="Candidate branch"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                  />
                  <span>next edit branch</span>
                </label>
              </div>
            )}
          </aside>
        )}
      </main>
      <footer className="statusbar">
        <div>
          <span className="live-dot" />
          <span>
            {connecting
              ? "Connecting to local service…"
              : jobRunning
                ? "Geometry worker active"
                : "Local workspace"}
          </span>
          <span className="footer-separator">/</span>
          <span>CadQuery · BREP</span>
        </div>
        <div>
          {revision && (
            <>
              <span>{features.length} features</span>
              <span>{parts.length} parts</span>
              <span className="footer-separator">/</span>
              <span className={failed ? "text-error" : "text-success"}>
                {checks.length
                  ? `${passed} of ${checks.length} checks passed`
                  : "Not yet measured"}
              </span>
            </>
          )}
          <span className="footer-separator">/</span>
          <span>mm internal</span>
        </div>
      </footer>
      {error && (
        <div className="global-error">
          <ErrorMessage error={error} clear={() => setError("")} />
        </div>
      )}
      {dialog === "library" && (
        <Library
          projects={projects}
          current={project?.id}
          onClose={() => setDialog(null)}
          onCreate={createProject}
          onGenerate={generateProject}
          configured={configured}
          onOpen={(id) => {
            run(async () => {
              await loadProject(id);
              setDialog(null);
              setCompareMesh(undefined);
              setComparison(undefined);
            });
          }}
          busy={busy}
        />
      )}
      {dialog === "reference" && selectedReference && (
        <ReferencePanel
          reference={selectedReference}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "import" && (
        <ImportPanel
          onClose={() => setDialog(null)}
          onImport={importFile}
          busy={busy}
        />
      )}
      {dialog === "export" && (
        <ExportPanel
          revision={visibleRevision}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "feature" && revision && (
        <FeatureDialog
          revision={revision}
          onClose={() => setDialog(null)}
          onSubmit={(feature) => edit({ add_features: [feature] })}
          busy={busy}
        />
      )}
      {dialog === "constraint" && revision && (
        <ConstraintDialog
          onClose={() => setDialog(null)}
          onSubmit={(constraint) =>
            edit({ constraints: [...constraints, constraint] })
          }
          busy={busy}
        />
      )}
      {dialog === "settings" && (
        <SettingsPanel
          settings={provider}
          onClose={() => setDialog(null)}
          onSaved={(data) => {
            setProvider(data);
            setNotice("Settings saved locally.");
          }}
        />
      )}
      {dialog === "scout" && (
        <ScoutPanel revision={revision} onClose={() => setDialog(null)} />
      )}
      {dialog === "help" && (
        <Modal
          title="A workbench for changes that hold"
          subtitle="Start with a recipe. Edit a candidate. Check geometry. Accept deliberately."
          onClose={() => setDialog(null)}
        >
          <div className="help-content">
            <p>
              Dimensions and named features form a parametric feature graph.
              Every edit creates a revision; failed candidates leave the last
              accepted geometry intact.
            </p>
            <p>
              Use <b>Requirements</b> to inspect actual measurements,
              tolerances, and failures. Mandatory unresolved checks block
              acceptance. Mesh point measurement in the viewport is a visual
              aid, with tessellation accuracy.
            </p>
            <p>
              Compare revisions in the same world frame using Revision history.
              Export STEP for BREP interchange, or the source bundle to rebuild
              with CadQuery. STEP does not recover the feature tree.
            </p>
            <p>
              <kbd>⌘ / Ctrl + Z</kbd> undo accepted revision ·{" "}
              <kbd>Shift + ⌘ / Ctrl + Z</kbd> redo · <kbd>Esc</kbd> clear
              selection.
            </p>
          </div>
        </Modal>
      )}
      {bottomTab === "revisions" &&
        revision &&
        project &&
        project.revisions.length > 1 && (
          <div className="compare-selector">
            <GitCompareArrows size={15} />
            <label>
              Compare current with{" "}
              <select
                aria-label="Compare revision"
                value={compareFrom}
                onChange={(e) => compare(e.target.value)}
              >
                <option value="">Choose revision</option>
                {project.revisions
                  .filter((r) => r.id !== revision.id)
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      r
                      {String(
                        project.revisions.findIndex(
                          (item) => item.id === r.id,
                        ) + 1,
                      ).padStart(2, "0")}{" "}
                      · {r.branch} · {r.status}
                    </option>
                  ))}
              </select>
            </label>
            {comparison && (
              <span>
                {
                  (comparison.changed_features || comparison.changed || [])
                    .length
                }{" "}
                changed features
              </span>
            )}
          </div>
        )}
    </div>
  );
}

function AxisGlyph() {
  return <span className="datum-glyph">⌖</span>;
}
function GridGlyph() {
  return <span className="datum-glyph">▱</span>;
}
function RequirementCard({
  constraint,
  measurement,
  busy,
  onUpdate,
  onSelect,
}: {
  constraint: Constraint;
  measurement?: any;
  busy: boolean;
  onUpdate: (constraint: Constraint) => void;
  onSelect: () => void;
}) {
  const [definition, setDefinition] = useState(
      JSON.stringify(constraint, null, 2),
    ),
    [error, setError] = useState("");
  useEffect(
    () => setDefinition(JSON.stringify(constraint, null, 2)),
    [constraint],
  );
  return (
    <article className="constraint-card">
      <div>
        <LockKeyhole size={13} />
        <b>{constraint.name || humanize(constraint.id)}</b>
        <Status status={measurement?.status} />
      </div>
      <p>{measurement?.explanation || humanize(constraint.type)}</p>
      {measurement && (
        <dl>
          <div>
            <dt>Measured</dt>
            <dd className="actual-summary">
              {measurementSummary(
                measurement.actual ?? measurement.measured,
                measurement.unit,
              )}
            </dd>
          </div>
          <div>
            <dt>Tolerance</dt>
            <dd>{measurementTolerances(measurement, constraint.type)}</dd>
          </div>
          <div className="method-row">
            <dt>Method</dt>
            <dd>{measurement.method || "BREP measurement"}</dd>
          </div>
        </dl>
      )}
      <details>
        <summary>Actual measurement details</summary>
        <pre>
          {JSON.stringify(
            measurement
              ? {
                  actual: measurement.actual,
                  expected: measurement.expected,
                  tolerances: measurement.tolerances || {
                    reported: measurement.tolerance,
                    unit: measurement.unit,
                  },
                  method: measurement.method,
                }
              : undefined,
            null,
            2,
          ) || "No measurement recorded."}
        </pre>
      </details>
      <details>
        <summary>Edit requirement & preservation</summary>
        <textarea
          aria-label={`${constraint.name || constraint.id} requirement definition`}
          className="code-input"
          value={definition}
          onChange={(e) => setDefinition(e.target.value)}
        />
        {error && <p className="text-error">{error}</p>}
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={constraint.required !== false}
            disabled={busy}
            onChange={(e) =>
              onUpdate({ ...constraint, required: e.target.checked })
            }
          />
          Mandatory for acceptance
        </label>
        <div className="feature-actions">
          <button
            className="quiet-button"
            disabled={busy}
            onClick={() => {
              try {
                onUpdate(JSON.parse(definition));
              } catch {
                setError("Enter a valid requirement JSON object.");
              }
            }}
          >
            Build requirement revision
          </button>
          <button className="text-button" onClick={onSelect}>
            Select feature
          </button>
        </div>
      </details>
    </article>
  );
}
function FeatureDetails({
  feature,
  features,
  onUpdate,
  onRemove,
  busy,
}: {
  feature: Feature;
  features: Feature[];
  onUpdate: (parameters: Json) => void;
  onRemove: () => void;
  busy: boolean;
}) {
  const [json, setJson] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    setJson(JSON.stringify(feature.parameters, null, 2));
    setError("");
  }, [feature.id, feature.parameters]);
  return (
    <div className="feature-details">
      <div className="dependency-label">INPUT DEPENDENCIES</div>
      <div className="dependency-chips">
        {feature.inputs?.length ? (
          feature.inputs.map((id) => (
            <span key={id}>
              {features.find((f) => f.id === id)?.name || id}
            </span>
          ))
        ) : (
          <span>Origin datum</span>
        )}
      </div>
      <details>
        <summary>Edit feature parameters</summary>
        <textarea
          aria-label="Feature parameters JSON"
          className="code-input"
          value={json}
          onChange={(e) => setJson(e.target.value)}
        />
        {error && <p className="text-error">{error}</p>}
        <div className="feature-actions">
          <button
            className="quiet-button"
            disabled={busy}
            onClick={() => {
              try {
                onUpdate(JSON.parse(json));
              } catch {
                setError("Enter a valid JSON object.");
              }
            }}
          >
            Build feature edit
          </button>
          <button
            className="icon-button danger"
            aria-label="Remove selected feature"
            title="Remove feature; dependent references are validated"
            disabled={busy}
            onClick={onRemove}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </details>
    </div>
  );
}
function Library({
  projects,
  current,
  onClose,
  onCreate,
  onGenerate,
  configured,
  onOpen,
  busy,
}: {
  projects: Project[];
  current?: string;
  onClose: () => void;
  onCreate: (name: string, recipe: string) => void;
  onGenerate: (name: string, instruction: string) => void;
  configured: boolean;
  onOpen: (id: string) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("Instrument enclosure"),
    [recipe, setRecipe] = useState("enclosure"),
    [fromIntent, setFromIntent] = useState(false),
    [generationInstruction, setGenerationInstruction] = useState("");
  return (
    <Modal
      title="Make room for your next idea."
      subtitle="Editable mechanical starting points, built from real geometry."
      onClose={onClose}
      wide
    >
      <div className="library-layout">
        <div className="creation-mode">
          <button
            className={!fromIntent ? "active" : ""}
            onClick={() => setFromIntent(false)}
          >
            <Box size={13} />
            Starting recipes
          </button>
          <button
            className={fromIntent ? "active" : ""}
            onClick={() => setFromIntent(true)}
          >
            <Sparkles size={13} />
            From intent
          </button>
        </div>
        {fromIntent ? (
          <div className="generation-input">
            <label>
              Describe the part
              <textarea
                aria-label="Generation instruction"
                value={generationInstruction}
                onChange={(e) => setGenerationInstruction(e.target.value)}
                placeholder="Describe the geometry, dimensions, and required relationships. English or Chinese."
              />
            </label>
            {!configured && (
              <p>
                <WifiOff size={13} /> Configure an OpenAI-compatible provider in
                settings to generate designs from natural language.
              </p>
            )}
          </div>
        ) : (
          <div className="recipe-grid">
            {recipes.map((r) => (
              <button
                key={r.id}
                className={`recipe-card ${recipe === r.id ? "active" : ""}`}
                onClick={() => {
                  setRecipe(r.id);
                  setName(r.name);
                }}
              >
                <div className={"recipe-art " + r.id}>
                  <img
                    className="recipe-thumbnail"
                    src={`/api/recipes/${r.id}/thumbnail.svg`}
                    alt={`${r.name} projected from generated BREP geometry`}
                  />
                  <span>{r.badge}</span>
                </div>
                <div className="recipe-card-content">
                  <b>{r.name}</b>
                  <p>{r.description}</p>
                  <span>
                    {r.dimensions}
                    <ChevronRight size={14} />
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
        <form
          className="create-project-form"
          onSubmit={(e) => {
            e.preventDefault();
            fromIntent
              ? onGenerate(name, generationInstruction)
              : onCreate(name, recipe);
          }}
        >
          <label>
            Project name
            <input
              aria-label="Project name"
              value={name}
              required
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={
              busy ||
              !name.trim() ||
              (fromIntent && (!configured || !generationInstruction.trim()))
            }
          >
            {busy ? (
              <LoaderCircle size={16} className="spinning" />
            ) : (
              <Plus size={16} />
            )}
            Create design
          </button>
        </form>
        {projects.length > 0 && (
          <>
            <div className="library-saved-heading">
              <h3>Saved locally</h3>
              <span>{projects.length} designs</span>
            </div>
            <div className="saved-projects">
              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => onOpen(p.id)}
                  className={current === p.id ? "active" : ""}
                >
                  <span className="saved-project-icon">
                    {p.active_revision_id ? (
                      <img
                        src={downloadUrl(p.active_revision_id, "assembly.svg")}
                        alt="Saved geometry projection"
                      />
                    ) : (
                      <Box size={20} />
                    )}
                  </span>
                  <div>
                    <b>{p.name}</b>
                    <span>
                      {humanize(p.recipe || p.family || "Parametric design")} ·{" "}
                      {p.id.slice(0, 8)}
                    </span>
                  </div>
                  {current === p.id ? (
                    <span className="tag">Open</span>
                  ) : (
                    <ArrowUpRight size={15} />
                  )}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
function ExportPanel({
  revision,
  onClose,
}: {
  revision?: Revision;
  onClose: () => void;
}) {
  const files = [
    {
      file: "assembly.step",
      name: "STEP assembly",
      description: "Real BREP geometry · assembly in millimeters",
      icon: <Box size={19} />,
    },
    {
      file: "assembly.stl",
      name: "STL mesh",
      description: "Tessellated surfaces · millimeter convention",
      icon: <Boxes size={19} />,
    },
    {
      file: "design.py",
      name: "Parametric source",
      description: "Self-contained CadQuery Python generator",
      icon: <FileCode2 size={19} />,
    },
    {
      file: "design.json",
      name: "DesignSpec",
      description: "Parameters, named features, and requirements",
      icon: <FileJson2 size={19} />,
    },
    {
      file: "report.json",
      name: "Measured report",
      description: "Actual measurements, tolerances, and outcomes",
      icon: <ShieldCheck size={19} />,
    },
    {
      file: "assembly.svg",
      name: "Orthographic SVG",
      description: "Projected model · not a certified drawing",
      icon: <Square size={19} />,
    },
  ];
  return (
    <Modal
      title="Take your geometry with you."
      subtitle={`Export the displayed ${revision?.status || ""} revision in its manufacturing position.`}
      onClose={onClose}
    >
      <div className="export-list">
        {files.map((f) => (
          <a
            key={f.file}
            href={revision ? downloadUrl(revision.id, f.file) : "#"}
            download
            className="export-row"
          >
            {f.icon}
            <div>
              <b>{f.name}</b>
              <span>{f.description}</span>
            </div>
            <ArrowDownToLine size={16} />
          </a>
        ))}
      </div>
      <a
        className="primary-button export-bundle"
        href={revision ? downloadUrl(revision.id, "bundle.zip") : "#"}
        download
      >
        <ArrowDownToLine size={16} />
        Download rebuild bundle
      </a>
      <p className="modal-note">
        Source needs the documented CadQuery version. Geometry checks share the
        CAD kernel and do not certify manufacturing or physical fit.
      </p>
    </Modal>
  );
}
function ImportPanel({
  onClose,
  onImport,
  busy,
}: {
  onClose: () => void;
  onImport: (file: File) => void;
  busy: boolean;
}) {
  const [file, setFile] = useState<File>();
  return (
    <Modal
      title="Bring in reference geometry"
      subtitle="STEP imports as direct geometry. STL remains a mesh reference."
      onClose={onClose}
    >
      <form
        className="modal-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) onImport(file);
        }}
      >
        <label>
          STEP or STL file
          <input
            aria-label="Reference geometry file"
            type="file"
            accept=".step,.stp,.stl"
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </label>
        <p className="modal-note">
          Maximum 32 MB. Import does not recover the original feature history.
          STEP geometry can be combined with supported new features and measured
          checks.
        </p>
        <button className="primary-button" disabled={busy || !file}>
          {busy ? (
            <LoaderCircle className="spinning" size={15} />
          ) : (
            <ArrowRight size={15} />
          )}
          Import reference
        </button>
      </form>
    </Modal>
  );
}
function ReferencePanel({
  reference,
  onClose,
}: {
  reference: Json;
  onClose: () => void;
}) {
  const [mesh, setMesh] = useState<MeshData>(),
    [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    fetch("/api/references/" + reference.id + "/file")
      .then((response) => {
        if (!response.ok)
          throw new Error("The stored reference could not be opened.");
        return response.arrayBuffer();
      })
      .then((buffer) => {
        const geometry = new STLLoader().parse(buffer);
        const position = geometry.getAttribute("position");
        const normal = geometry.getAttribute("normal");
        const part = {
          id: reference.id,
          name: reference.name,
          vertices: Array.from(position.array),
          normals: Array.from(normal.array),
          indices: Array.from({ length: position.count }, (_, i) => i),
        };
        if (current) setMesh({ parts: [part] });
        geometry.dispose();
      })
      .catch((e) => setError(e.message));
    return () => {
      current = false;
    };
  }, [reference.id]);
  return (
    <Modal
      title={reference.name}
      subtitle="STL mesh reference · coordinates interpreted in millimeters · no recovered feature history"
      onClose={onClose}
      wide
    >
      <div className="reference-preview">
        <Viewport
          data={mesh}
          hidden={new Set()}
          onSelect={() => {}}
          revisionLabel="Mesh reference"
          meshOnly
        />
      </div>
      <div className="reference-footer">
        {error && <ErrorMessage error={error} />}
        <p className="modal-note">
          This reference has no BREP or parametric guarantees. Viewport point
          measurements are approximate mesh measurements.
        </p>
        <a
          className="quiet-button"
          href={"/api/references/" + reference.id + "/file"}
          download
        >
          <ArrowDownToLine size={13} />
          Download original reference
        </a>
      </div>
    </Modal>
  );
}
const featureTemplates: Record<string, Json> = {
  hole: { centers: [[0, 0, 0]], diameter: 3, depth: 40, start: -1, axis: "Z" },
  pocket: { size: [12, 8, 4], center: [0, 0, 26] },
  slot: { size: [12, 4, 5], center: [0, -24, 15] },
  fillet: { radius: 0.6, selector: "outer_vertical" },
  chamfer: { length: 0.5, selector: "outer_vertical" },
  box: { size: [10, 10, 10], center: [0, 0, 5] },
  cylinder: { diameter: 8, height: 10, center: [0, 0, 0] },
  pattern: {
    profile: "cylinder",
    centers: [
      [-20, 0, 0],
      [20, 0, 0],
    ],
    diameter: 8,
    height: 10,
    z: 0,
  },
  transform: { translation: [0, 0, 0], rotation: [0, 0, 0] },
  extrude: {
    points: [
      [-5, -5],
      [5, -5],
      [5, 5],
      [-5, 5],
    ],
    height: 10,
  },
};
function FeatureDialog({
  revision,
  onClose,
  onSubmit,
  busy,
}: {
  revision: Revision;
  onClose: () => void;
  onSubmit: (feature: Feature) => void;
  busy: boolean;
}) {
  const [type, setType] = useState("slot"),
    [part, setPart] = useState(revision.spec.parts[0]?.id || ""),
    [name, setName] = useState("Connector cutout"),
    [id, setId] = useState("connector_cutout"),
    [json, setJson] = useState(JSON.stringify(featureTemplates.slot, null, 2)),
    [error, setError] = useState(""),
    [input, setInput] = useState(revision.spec.parts[0]?.feature || "");
  return (
    <Modal
      title="Insert a named feature"
      subtitle="Add a feature to the graph. Required references are validated before building."
      onClose={onClose}
    >
      <form
        className="modal-form"
        onSubmit={(e) => {
          e.preventDefault();
          try {
            const parameters = JSON.parse(json);
            onSubmit({
              id,
              name,
              type,
              part,
              inputs: input ? [input] : [],
              parameters,
            });
          } catch {
            setError("Parameters must be a valid JSON object.");
          }
        }}
      >
        <div className="form-two">
          <label>
            Feature type
            <select
              aria-label="Feature type"
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                setJson(
                  JSON.stringify(featureTemplates[e.target.value], null, 2),
                );
              }}
            >
              {Object.keys(featureTemplates).map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Part
            <select
              aria-label="Feature part"
              value={part}
              onChange={(e) => {
                setPart(e.target.value);
                setInput(
                  revision.spec.parts.find((p) => p.id === e.target.value)
                    ?.feature || "",
                );
              }}
            >
              {revision.spec.parts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.id}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-two">
          <label>
            Name
            <input
              aria-label="Feature name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <label>
            Semantic ID
            <input
              aria-label="Feature ID"
              value={id}
              onChange={(e) => setId(e.target.value)}
              pattern="[a-zA-Z][a-zA-Z0-9_-]*"
              required
            />
          </label>
        </div>
        <label>
          Input feature
          <select
            aria-label="Input feature"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          >
            <option value="">Origin / independent primitive</option>
            {revision.spec.features
              .filter((f) => f.part === part)
              .map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name || f.id}
                </option>
              ))}
          </select>
        </label>
        <label>
          Parameters{" "}
          <span className="muted">
            Lengths in design units. Expressions may reference named parameters.
          </span>
          <textarea
            aria-label="New feature parameters"
            className="code-input"
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        {error && <ErrorMessage error={error} />}
        <button className="primary-button" type="submit" disabled={busy}>
          Insert & build candidate <ArrowRight size={14} />
        </button>
      </form>
    </Modal>
  );
}
function ConstraintDialog({
  onClose,
  onSubmit,
  busy,
}: {
  onClose: () => void;
  onSubmit: (constraint: Constraint) => void;
  busy: boolean;
}) {
  const [json, setJson] = useState(
      JSON.stringify(
        {
          id: "internal_clearance",
          name: "Internal clearance",
          type: "keepout",
          required: true,
          features: ["body_cavity"],
          tolerance: 0.01,
          parameters: {
            part: "body",
            size: [40, 20, 16],
            center: [0, 0, 12],
            max_volume: 0.001,
          },
        },
        null,
        2,
      ),
    ),
    [error, setError] = useState("");
  return (
    <Modal
      title="Add a geometry requirement"
      subtitle="Define a measured requirement; unsupported checks are reported as unknown."
      onClose={onClose}
    >
      <form
        className="modal-form"
        onSubmit={(e) => {
          e.preventDefault();
          try {
            onSubmit(JSON.parse(json));
          } catch {
            setError("Enter a valid constraint JSON object.");
          }
        }}
      >
        <label>
          Requirement definition
          <textarea
            aria-label="Requirement JSON"
            className="code-input large"
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        <p className="modal-note">
          Supported types include envelope, hole_pattern, thickness, keepout,
          interference, and clearance. Required checks must pass before
          acceptance.
        </p>
        {error && <ErrorMessage error={error} />}
        <button className="primary-button" disabled={busy}>
          Add & measure requirement <ArrowRight size={14} />
        </button>
      </form>
    </Modal>
  );
}
function SettingsPanel({
  settings,
  onClose,
  onSaved,
}: {
  settings: Json;
  onClose: () => void;
  onSaved: (data: Json) => void;
}) {
  const [provider, setProvider] = useState({
      ...(settings.provider || settings),
    }),
    [worker, setWorker] = useState({
      ...(settings.workers || {
        timeout_seconds: 120,
        memory_mb: 4096,
        max_queue: 16,
      }),
    }),
    [key, setKey] = useState(""),
    [status, setStatus] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      const data = await api(
        "/settings",
        {
          provider: {
            endpoint: provider.endpoint || "",
            model: provider.model || "",
            timeout_seconds: Number(provider.timeout_seconds) || 30,
            max_tokens: Number(provider.max_tokens) || 4096,
            ...(key ? { api_key: key } : {}),
          },
          workers: worker,
        },
        "PUT",
      );
      onSaved(data);
      setStatus("Settings saved.");
      setKey("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function probe() {
    await save();
    setBusy(true);
    try {
      const data = await api("/provider/probe", {});
      setStatus(
        data.connected
          ? `Connected · ${data.models?.length || 0} available models · ${data.structured_output || "structured output capability unknown"}`
          : data.error || "Connection failed.",
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Your workspace, your tools."
      subtitle="Credentials stay on the local backend. Structured editing works without a model."
      onClose={onClose}
    >
      <div className="modal-form">
        <h3 className="form-section-title">
          <Sparkles size={16} />
          Language provider
        </h3>
        <label>
          OpenAI-compatible endpoint
          <input
            aria-label="Provider endpoint"
            placeholder="http://localhost:11434/v1"
            value={provider.endpoint || ""}
            onChange={(e) =>
              setProvider({ ...provider, endpoint: e.target.value })
            }
          />
        </label>
        <div className="form-two">
          <label>
            Model
            <input
              aria-label="Provider model"
              placeholder="Model ID from your provider"
              value={provider.model || ""}
              onChange={(e) =>
                setProvider({ ...provider, model: e.target.value })
              }
            />
          </label>
          <label>
            API key
            <input
              aria-label="Provider API key"
              type="password"
              autoComplete="off"
              placeholder={
                settings.provider?.has_api_key
                  ? "Saved on server"
                  : "Optional for local providers"
              }
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </label>
        </div>
        <div className="form-two">
          <label>
            Request timeout (seconds)
            <input
              type="number"
              min="1"
              max="180"
              value={provider.timeout_seconds || 30}
              onChange={(e) =>
                setProvider({
                  ...provider,
                  timeout_seconds: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Maximum output tokens
            <input
              type="number"
              min="256"
              max="16000"
              value={provider.max_tokens || 4096}
              onChange={(e) =>
                setProvider({ ...provider, max_tokens: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <h3 className="form-section-title">
          <Cog size={16} />
          Geometry workers
        </h3>
        <div className="form-two">
          <label>
            Build timeout (seconds)
            <input
              aria-label="Worker timeout"
              type="number"
              min="5"
              max="600"
              value={worker.timeout_seconds || 120}
              onChange={(e) =>
                setWorker({
                  ...worker,
                  timeout_seconds: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Memory ceiling (MB)
            <input
              aria-label="Worker memory ceiling"
              type="number"
              min="512"
              step="256"
              value={worker.memory_mb || 2048}
              onChange={(e) =>
                setWorker({ ...worker, memory_mb: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <p className="modal-note">
          Geometry runs in isolated processes. Changing limits applies to future
          jobs.
        </p>
        {error && <ErrorMessage error={error} />}{" "}
        {status && (
          <p role="status" className="settings-status">
            {status}
          </p>
        )}
        <div className="storage-cleanup">
          <p>
            Remove scratch files from failed or cancelled jobs. Saved designs
            and accepted exports are retained.
          </p>
          <button
            className="quiet-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const data = await api("/storage/cleanup", {
                  failed_jobs: true,
                  scout_cache: false,
                });
                setStatus(
                  `Removed ${data.removed_job_directories ?? data.removed_jobs ?? data.removed ?? 0} job scratch directories.`,
                );
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Trash2 size={13} />
            Clean scratch files
          </button>
        </div>
        <div className="modal-actions">
          <button className="quiet-button" onClick={probe} disabled={busy}>
            Save & test connection
          </button>
          <button className="primary-button" onClick={save} disabled={busy}>
            {busy ? (
              <LoaderCircle size={15} className="spinning" />
            ) : (
              <Check size={15} />
            )}
            Save settings
          </button>
        </div>
      </div>
    </Modal>
  );
}
function ScoutPanel({
  revision,
  onClose,
}: {
  revision?: Revision;
  onClose: () => void;
}) {
  const [cards, setCards] = useState<Json[]>([]),
    [status, setStatus] = useState<Json>({}),
    [settings, setSettings] = useState<Json>({
      network_enabled: false,
      sources: [],
      interval_seconds: 3600,
      model_budget: 0,
    }),
    [operation, setOperation] = useState("fillet"),
    [problem, setProblem] = useState(
      revision?.error ? formatValue(revision.error) : "",
    ),
    [budget, setBudget] = useState(3),
    [error, setError] = useState(""),
    [outcome, setOutcome] = useState(""),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState("library");
  const refresh = useCallback(async () => {
    const [s, c] = await Promise.all([
      api("/scout/status"),
      api<any>("/scout/cards"),
    ]);
    setStatus(s);
    setSettings({
      network_enabled: s.network_enabled,
      sources: s.sources || [],
      interval_seconds: s.interval_seconds || 3600,
      model_budget: s.model_budget || 0,
      enabled: false,
    });
    setCards(Array.isArray(c) ? c : c.cards || []);
  }, []);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);
  async function act(path: string, body: Json = {}) {
    setBusy(true);
    setError("");
    try {
      const result = await api("/scout/" + path, body);
      setOutcome(
        result.unresolved?.join(" ") ||
          result.message ||
          `Operation completed. ${result.fetched?.length || 0} sources retrieved; ${result.cached_count ?? result.cards?.length ?? 0} cached results.`,
      );
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function saveSettings() {
    setBusy(true);
    try {
      await api(
        "/settings",
        {
          scout: {
            network_enabled: settings.network_enabled,
            sources: settings.sources,
            interval_seconds: settings.interval_seconds,
            model_budget: settings.model_budget,
            enabled: settings.enabled || false,
          },
        },
        "PUT",
      );
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="SolutionScout"
      subtitle="Source-grounded guidance. Proposed repairs never change your design silently."
      onClose={onClose}
      wide
    >
      <div className="scout-layout">
        <div className="scout-toolbar">
          <div className="scout-tabs">
            <button
              className={tab === "library" ? "active" : ""}
              onClick={() => setTab("library")}
            >
              Solution library <span>{cards.length}</span>
            </button>
            <button
              className={tab === "investigate" ? "active" : ""}
              onClick={() => setTab("investigate")}
            >
              Investigate
            </button>
            <button
              className={tab === "sources" ? "active" : ""}
              onClick={() => setTab("sources")}
            >
              Sources & watch
            </button>
          </div>
          <span className="provider-chip">
            <span
              className={settings.network_enabled ? "live-dot" : "offline-dot"}
            />
            {settings.network_enabled ? "Network enabled" : "Cached / offline"}
          </span>
        </div>
        {error && <ErrorMessage error={error} />}{" "}
        {busy && (
          <div className="scout-operation">
            <LoaderCircle className="spinning" size={14} />
            <span>
              Retrieving sources or reproducing on a disposable model…
            </span>
            <button
              onClick={() =>
                api("/scout/cancel", {})
                  .then(() =>
                    setOutcome(
                      "Cancellation requested; useful cached results are preserved.",
                    ),
                  )
                  .catch((e) => setError(e.message))
              }
            >
              Cancel operation
            </button>
          </div>
        )}
        {outcome && (
          <p role="status" className="scout-outcome">
            {outcome}
          </p>
        )}{" "}
        {tab === "library" && (
          <div className="scout-cards">
            {cards.map((card: any) => (
              <article className="solution-card" key={card.id}>
                <div>
                  <span className={`solution-state ${card.status}`}>
                    {card.status || "sourced"}
                  </span>
                  <span className="muted">
                    {card.freshness ||
                      card.fetched_at?.slice(0, 10) ||
                      "Freshness unknown"}
                  </span>
                </div>
                <h3>{card.problem || card.title || "Geometry guidance"}</h3>
                <p>{card.mechanism || card.proposed_mechanism}</p>
                <div className="solution-limits">
                  <b>Applicability</b>{" "}
                  {typeof card.applicability === "object"
                    ? formatValue(card.applicability)
                    : card.applicability ||
                      card.limitations ||
                      "Read the source and limitations before use."}
                </div>
                <details>
                  <summary>Evidence, reproduction & limits</summary>
                  <dl>
                    <div>
                      <dt>Compatible versions</dt>
                      <dd>{formatValue(card.compatible_versions)}</dd>
                    </div>
                    <div>
                      <dt>Adaptation</dt>
                      <dd>
                        {formatValue(
                          card.adaptation || card.adaptation_instructions,
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Actual outcome</dt>
                      <dd>{formatValue(card.outcome)}</dd>
                    </div>
                    <div>
                      <dt>Limitations</dt>
                      <dd>{formatValue(card.limitations)}</dd>
                    </div>
                    <div>
                      <dt>License notes</dt>
                      <dd>{formatValue(card.license_notes)}</dd>
                    </div>
                  </dl>
                  <code className="reproduction-command">
                    {card.reproduction_command ||
                      "No local reproduction recorded."}
                  </code>
                  {(card.source_urls || []).map((url: string) => (
                    <a key={url} href={url} target="_blank" rel="noreferrer">
                      {new URL(url).hostname}
                      <ArrowUpRight size={12} />
                    </a>
                  ))}
                </details>
              </article>
            ))}
            {!cards.length && (
              <div className="knowledge-empty">
                <Search size={30} />
                <h3>Build a library of tested mechanisms.</h3>
                <p>
                  Index your selected official references or investigate an
                  active geometry problem. Offline mode uses cached sources.
                </p>
                <button
                  className="primary-button"
                  onClick={() => act("sync")}
                  disabled={busy}
                >
                  Index sources
                </button>
              </div>
            )}
          </div>
        )}
        {tab === "investigate" && (
          <form
            className="modal-form"
            onSubmit={(e) => {
              e.preventDefault();
              act("ask", {
                operation,
                error: problem,
                feature_graph: revision?.spec.features || [],
                geometry: {
                  family: revision?.spec.family,
                  units: revision?.spec.units,
                  part_count: revision?.spec.parts.length,
                },
                invariants: revision?.spec.constraints || [],
                budget: {
                  max_fetches: budget,
                  max_reproductions: 1,
                  max_seconds: 30,
                },
                allow_private_query: false,
              });
            }}
          >
            <div className="form-two">
              <label>
                Operation
                <input
                  aria-label="Scout operation"
                  value={operation}
                  onChange={(e) => setOperation(e.target.value)}
                />
              </label>
              <label>
                Source retrieval budget
                <input
                  aria-label="Scout budget"
                  type="number"
                  min="1"
                  max="10"
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                />
              </label>
            </div>
            <label>
              Failure or question
              <textarea
                aria-label="Scout problem"
                value={problem}
                onChange={(e) => setProblem(e.target.value)}
                placeholder="Describe the kernel failure or mechanism you need…"
                required
              />
            </label>
            <p className="modal-note">
              Search queries exclude private feature dimensions and
              instructions. Source search is available without a model;
              retrieval alone is not autonomous reasoning.
            </p>
            <button className="primary-button" disabled={busy}>
              {busy ? (
                <LoaderCircle size={16} className="spinning" />
              ) : (
                <Search size={16} />
              )}
              Investigate problem
            </button>
          </form>
        )}
        {tab === "sources" && (
          <div className="modal-form">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={!!settings.network_enabled}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    network_enabled: e.target.checked,
                  })
                }
              />
              Allow selected source retrieval over the network
            </label>
            <label>
              Official documentation and repository source URLs
              <textarea
                aria-label="Scout sources"
                value={(settings.sources || []).join("\n")}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    sources: e.target.value.split("\n").filter(Boolean),
                  })
                }
                placeholder="One HTTPS URL per line"
              />
            </label>
            <div className="form-two">
              <label>
                Refresh interval (seconds)
                <input
                  aria-label="Scout refresh interval"
                  type="number"
                  min="30"
                  value={settings.interval_seconds || 3600}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      interval_seconds: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Model budget per refresh
                <input
                  aria-label="Scout model budget"
                  type="number"
                  min="0"
                  value={settings.model_budget || 0}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      model_budget: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
            <div className="watch-status">
              <span
                className={
                  status.running || status.watch_running
                    ? "live-dot"
                    : "offline-dot"
                }
              />
              <div>
                <b>
                  {status.running || status.watch_running
                    ? "Watch is running"
                    : "Watch is stopped"}
                </b>
                <span>
                  {status.last_error ||
                    status.last_sync ||
                    "No refresh recorded"}
                </span>
              </div>
            </div>
            <div className="modal-actions">
              <button
                className="quiet-button"
                onClick={() => act("sync")}
                disabled={busy}
              >
                Refresh now
              </button>
              <button
                className="quiet-button"
                onClick={async () => {
                  if (!(status.running || status.watch_running))
                    await saveSettings();
                  act(
                    status.running || status.watch_running ? "stop" : "watch",
                  );
                }}
                disabled={busy}
              >
                {status.running || status.watch_running
                  ? "Stop watch"
                  : "Start watch"}
              </button>
              <button
                className="primary-button"
                onClick={saveSettings}
                disabled={busy}
              >
                Save source settings
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

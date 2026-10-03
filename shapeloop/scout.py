"""Source-indexed CAD guidance with bounded retrieval and disposable reproductions.

Fetched text is indexed as evidence only. It is never imported, evaluated or executed.
"""
from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_SOURCES = [
    "https://cadquery.readthedocs.io/en/latest/selectors.html",
    "https://cadquery.readthedocs.io/en/latest/importexport.html",
    "https://cadquery.readthedocs.io/en/latest/classreference.html",
    "https://raw.githubusercontent.com/CadQuery/cadquery/master/tests/test_cadquery.py",
    "https://raw.githubusercontent.com/CadQuery/cadquery/master/cadquery/cq.py",
    "https://cadquery.readthedocs.io/en/latest/assy.html",
]
SAFE_SOURCE_PREFIXES = (
    "https://cadquery.readthedocs.io/en/",
    "https://raw.githubusercontent.com/CadQuery/cadquery/",
    "https://raw.githubusercontent.com/CadQuery/OCP/",
    "https://github.com/CadQuery/cadquery/",
    "https://github.com/CadQuery/OCP/",
    "https://dev.opencascade.org/doc/",
    "https://occt3d.com/dev/doc/",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def installed_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for package in ("cadquery", "cadquery-ocp"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def validate_source(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port:
        raise ValueError("Scout sources must be plain HTTPS URLs without credentials, port, query or fragment")
    if not any(url.startswith(prefix) for prefix in SAFE_SOURCE_PREFIXES):
        raise ValueError("Scout sources are limited to CadQuery/OCP repositories and official CAD documentation")
    # Bound traversal and encoded separators; no network path is supplied to a shell or local filesystem.
    if ".." in parsed.path or "%" in parsed.path:
        raise ValueError("Encoded or traversing source paths are unsupported")
    return url


class ScoutSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network_enabled: bool = False
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SOURCES), max_length=30)
    interval_seconds: float = Field(default=3600, ge=30, le=604800)
    model_budget: int = Field(default=0, ge=0, le=10)
    enabled: bool = False
    max_source_bytes: int = Field(default=500_000, ge=1024, le=2_000_000)
    freshness_hours: float = Field(default=168, ge=0.01, le=8760)

    @field_validator("sources")
    @classmethod
    def sources_safe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(validate_source(url) for url in value))


class InvestigationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_fetches: int = Field(default=3, ge=0, le=30)
    max_bytes: int = Field(default=1_000_000, ge=0, le=10_000_000)
    max_seconds: float = Field(default=30, ge=1, le=120)
    max_reproductions: int = Field(default=1, ge=0, le=3)
    model_calls: int = Field(default=0, ge=0, le=10)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(max_length=100)
    error: str = Field(default="", max_length=4000)
    feature_graph: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    geometry: dict[str, Any] | str = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=installed_versions)
    invariants: list[Any] = Field(default_factory=list)
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)
    reproduce: bool = True
    allow_private_query: bool = False


class SolutionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    problem: str
    operation: str
    status: Literal["sourced", "reproduced", "rejected", "stale"] = "sourced"
    source_urls: list[str]
    source_files: list[str] = Field(default_factory=list)
    source_excerpt: str = ""
    compatible_versions: dict[str, str] = Field(default_factory=dict)
    mechanism: str
    adaptation: str
    reproduction_command: str = ""
    outcome: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    license_notes: list[str] = Field(default_factory=list)
    fetched_at: str
    created_at: str = Field(default_factory=utcnow)
    freshness: str = "current source snapshot; local version applicability untested"
    applicability: str
    source_hashes: dict[str, str] = Field(default_factory=dict)
    retrieval_mode: str = "deterministic source lookup; no model reasoning"
    promoted: bool = False
    local_context: dict[str, Any] = Field(default_factory=dict)


class ScoutStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS scout_sources (url TEXT PRIMARY KEY, content TEXT NOT NULL, content_hash TEXT NOT NULL, fetched_at TEXT NOT NULL, error TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS solution_cards (id TEXT PRIMARY KEY, operation TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS scout_events (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def cache_source(self, url: str, content: str) -> dict[str, Any]:
        row = {"url": url, "content": content, "content_hash": hashlib.sha256(content.encode()).hexdigest(), "fetched_at": utcnow(), "error": None}
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO scout_sources VALUES (:url,:content,:content_hash,:fetched_at,:error)", row)
        return row

    def sources(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM scout_sources ORDER BY url")]

    def put_card(self, card: SolutionCard) -> SolutionCard:
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO solution_cards VALUES (?,?,?,?)", (card.id, card.operation, card.created_at, card.model_dump_json()))
        return card

    def cards(self, operation: str | None = None) -> list[SolutionCard]:
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM solution_cards WHERE operation=? ORDER BY created_at DESC LIMIT 500", (operation,)) if operation else db.execute("SELECT payload FROM solution_cards ORDER BY created_at DESC LIMIT 500")
            return [SolutionCard.model_validate_json(row[0]) for row in rows]

    def log(self, event: dict[str, Any]):
        with self.connection() as db:
            db.execute("INSERT INTO scout_events(created_at,payload) VALUES (?,?)", (utcnow(), json.dumps(event)))

    def clear(self, *, sources: bool = False):
        with self.connection() as db:
            db.execute("DELETE FROM solution_cards")
            db.execute("DELETE FROM scout_events")
            if sources:
                db.execute("DELETE FROM scout_sources")


class ScoutCancelled(RuntimeError):
    pass


class FetchBudgetError(ValueError):
    def __init__(self, message: str, consumed: int):
        super().__init__(message)
        self.consumed = consumed


class SolutionScout:
    def __init__(self, store: ScoutStore | str | Path, settings: ScoutSettings | dict[str, Any] | None = None, *, versions: dict[str, str] | None = None, transport: httpx.BaseTransport | None = None):
        self.store = store if isinstance(store, ScoutStore) else ScoutStore(store)
        self.settings = settings if isinstance(settings, ScoutSettings) else ScoutSettings.model_validate(settings or {})
        self.versions = versions or installed_versions()
        self.transport = transport
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._watch: threading.Thread | None = None
        self._foreground = threading.Event()
        self._operation_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state: dict[str, Any] = {"last_sync": None, "last_error": None, "active_operation": None}

    def _check(self, cancel: threading.Event | None, deadline: float):
        if self._cancel.is_set() or (cancel and cancel.is_set()):
            raise ScoutCancelled("Scout operation cancelled; cached partial work is preserved")
        if time.monotonic() >= deadline:
            raise ScoutCancelled("Scout time budget exhausted; cached partial work is preserved")

    def _fetch(self, url: str, max_bytes: int, deadline: float, cancel: threading.Event | None) -> str:
        validate_source(url)
        # Every redirect is checked against the allowlist. No user geometry is sent in URLs or headers.
        for _ in range(4):
            self._check(cancel, deadline)
            with httpx.Client(timeout=min(8, max(0.1, deadline - time.monotonic())), follow_redirects=False, transport=self.transport, trust_env=False) as client:
                with client.stream("GET", url, headers={"User-Agent": "ShapeLoop-CAD-SolutionScout/0.1", "Accept": "text/html,text/plain"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        from urllib.parse import urljoin
                        url = validate_source(urljoin(url, response.headers.get("location", "")))
                        continue
                    response.raise_for_status()
                    declared_size = response.headers.get("content-length", "")
                    if declared_size.isdigit() and int(declared_size) > max_bytes:
                        raise FetchBudgetError("Source exceeds fetch byte budget", 0)
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(kind in content_type for kind in ("text/", "application/json")):
                        raise ValueError("Unsupported binary source response")
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=min(8192, max_bytes)):
                        self._check(cancel, deadline)
                        if len(data) + len(chunk) > max_bytes:
                            raise FetchBudgetError("Source exceeds fetch byte budget", len(data) + len(chunk))
                        data.extend(chunk)
                    return bytes(data).decode("utf-8", errors="replace")
        raise ValueError("Source redirects exceed limit")

    def sync(self, *, budget: InvestigationBudget | dict[str, Any] | None = None, cancel: threading.Event | None = None, sources: list[str] | None = None) -> dict[str, Any]:
        request_budget = budget if isinstance(budget, InvestigationBudget) else InvestigationBudget.model_validate(budget or {"max_fetches": len(self.settings.sources), "max_bytes": 3_000_000})
        source_list = self.settings.sources if sources is None else [validate_source(url) for url in sources]
        with self._operation_lock:
            self._cancel.clear()
            with self._state_lock:
                self._state["active_operation"] = "sync"
            result: dict[str, Any] = {"fetched": [], "errors": [], "network_enabled": self.settings.network_enabled, "bytes": 0, "cancelled": False}
            deadline = time.monotonic() + request_budget.max_seconds
            try:
                if self.settings.network_enabled:
                    for url in source_list[:request_budget.max_fetches]:
                        self._check(cancel, deadline)
                        remaining = request_budget.max_bytes - result["bytes"]
                        if remaining <= 0:
                            result["errors"].append({"url": url, "error": "Fetch byte budget exhausted"})
                            break
                        try:
                            content = self._fetch(url, min(remaining, self.settings.max_source_bytes), deadline, cancel)
                            self.store.cache_source(url, content)
                            result["fetched"].append(url)
                            result["bytes"] += len(content.encode("utf-8"))
                        except ScoutCancelled:
                            raise
                        except (httpx.HTTPError, ValueError) as exc:
                            if isinstance(exc, FetchBudgetError):
                                result["bytes"] += exc.consumed
                            result["errors"].append({"url": url, "error": "Source fetch failed" if isinstance(exc, httpx.HTTPError) else str(exc)})
                result["cached_count"] = len(self.store.sources())
                if not self.settings.network_enabled:
                    result["message"] = "Network disabled; existing cached sources retained"
            except ScoutCancelled as exc:
                result["cancelled"] = True
                result["message"] = str(exc)
            finally:
                with self._state_lock:
                    self._state.update(active_operation=None, last_sync=utcnow(), last_error=result["errors"][-1]["error"] if result["errors"] else None)
                self.store.log({"operation": "sync", **result})
            return result

    def _fresh_cards(self, operation: str, versions: dict[str, str]) -> list[SolutionCard]:
        sources = {row["url"]: row for row in self.store.sources()}
        cards = self.store.cards(operation)
        for card in cards:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(card.fetched_at)).total_seconds() / 3600
            version_changed = bool(card.compatible_versions) and any(versions.get(key) != value for key, value in card.compatible_versions.items())
            changed = any(url not in sources or sources[url]["content_hash"] != value for url, value in card.source_hashes.items())
            if age > self.settings.freshness_hours or version_changed or changed:
                card.status = "stale"
                card.promoted = False
                card.freshness = "Stale: installed version, source content, or age differs from tested snapshot"
                self.store.put_card(card)
            elif not self.settings.network_enabled:
                card.freshness = "Cached snapshot; source freshness has not been checked while offline"
        return cards

    def cards(self) -> list[dict[str, Any]]:
        operations = {card.operation for card in self.store.cards()}
        return [card.model_dump() for operation in sorted(operations) for card in self._fresh_cards(operation, self.versions)]

    def ask(self, request: InvestigationRequest | dict[str, Any], *, cancel: threading.Event | None = None) -> dict[str, Any]:
        request = request if isinstance(request, InvestigationRequest) else InvestigationRequest.model_validate(request)
        started = time.monotonic()
        # Only controlled operation terms select external references. Raw errors, dimensions, and feature names stay local.
        operation = normalize_operation(request.operation)
        versions = request.versions or self.versions
        cached = self._fresh_cards(operation, versions)
        reproduction_requested = request.reproduce and request.budget.max_reproductions > 0 and operation in {"fillet", "selector", "step", "boolean"}
        reusable = [card for card in cached if card.status == "reproduced" or (card.status == "sourced" and not reproduction_requested)]
        if reusable:
            return {"cards": [card.model_dump() for card in reusable], "cache_hit": True, "retrieval_mode": "deterministic source lookup; no model reasoning", "model_calls": 0, "unresolved": ["Guidance does not establish acceptance of the active design"]}
        candidate_sources = sorted(self.settings.sources, key=lambda url: source_score(url, operation), reverse=True)
        if any(card.status == "sourced" for card in cached):
            sync_result = {"fetched": [], "errors": [], "bytes": 0, "message": "Reproduce previously sourced cached guidance before fetching more"}
        else:
            self._foreground.set()
            if self.status()["active_operation"] == "sync" and self._watch and self._watch.is_alive():
                self._cancel.set()
            try:
                sync_result = self.sync(budget=request.budget, cancel=cancel, sources=candidate_sources)
            finally:
                self._foreground.clear()
        if sync_result.get("cancelled"):
            return {"cards": [card.model_dump() for card in cached], "cache_hit": False, "cancelled": True, "unresolved": [sync_result["message"]], "model_calls": 0}
        sources = self.store.sources()
        ranked = sorted(sources, key=lambda row: source_score(row["url"], operation) + text_score(row["content"], operation), reverse=True)
        if not ranked or text_score(ranked[0]["content"], operation) == 0:
            return {"cards": [card.model_dump() for card in cached], "cache_hit": False, "unresolved": ["No relevant indexed source; enable network and select a relevant official source"], "retrieval_mode": "deterministic source lookup; no model reasoning", "model_calls": 0, "sync": sync_result}
        selected = ranked[:2]
        mechanism, adaptation, applicability, alternatives = guidance(operation)
        card = SolutionCard(problem=f"Investigate CadQuery {operation}", operation=operation, source_urls=[row["url"] for row in selected], source_files=[row["url"].split("/master/")[-1] for row in selected if "raw.githubusercontent.com" in row["url"]], source_excerpt=excerpt(selected[0]["content"], operation), mechanism=mechanism, adaptation=adaptation, applicability=applicability, alternatives=alternatives, fetched_at=min(row["fetched_at"] for row in selected), source_hashes={row["url"]: row["content_hash"] for row in selected}, limitations=["Source-derived suggestion; not evidence that the active model passes any required check", "A simple-box reproduction cannot establish applicability to arbitrary enclosure topology"], license_notes=["CadQuery source is Apache-2.0; documentation/source references are evidence, not bundled application code", "OpenCascade/native dependencies retain their own license terms"])
        card.problem = f"{request.operation}: {request.error}".strip(": ")
        card.local_context = {"feature_graph": request.feature_graph, "minimal_geometry": request.geometry, "required_invariants": request.invariants, "requested_versions": versions, "private_query_sent": False}
        remaining_seconds = request.budget.max_seconds - (time.monotonic() - started)
        if request.reproduce and request.budget.max_reproductions > 0 and operation in {"fillet", "selector", "step", "boolean"} and remaining_seconds > 0:
            self._foreground.set()
            with self._operation_lock:
                self._cancel.clear()
                with self._state_lock:
                    self._state["active_operation"] = "reproduce"
                try:
                    outcome = self._reproduce(operation, timeout=min(remaining_seconds, 30), cancel=cancel)
                    card.outcome = outcome
                    card.reproduction_command = f"python -m shapeloop.scout --reproduce {operation}"
                    if outcome.get("success"):
                        card.status = "reproduced"
                        card.compatible_versions = self.versions
                        card.promoted = len(outcome.get("variants", [])) >= 3
                        card.freshness = "Locally reproduced on three fixed disposable variants with the exact listed installed versions"
                    else:
                        card.status = "rejected"
                        card.freshness = "Local reproduction failed or was cancelled; this remedy is not tested working guidance"
                finally:
                    self._foreground.clear()
                    with self._state_lock:
                        self._state["active_operation"] = None
        self.store.put_card(card)
        self.store.log({"operation": "ask", "kind": operation, "card_id": card.id, "status": card.status, "private_query_sent": False, "model_calls": 0})
        return {"cards": [card.model_dump()], "cache_hit": False, "sync": sync_result, "retrieval_mode": card.retrieval_mode, "model_calls": 0, "unresolved": ["Apply any repair as an explicit candidate, then rerun active-design verification"]}

    def _reproduce(self, operation: str, *, timeout: float, cancel: threading.Event | None) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="shapeloop-scout-") as scratch:
            # This command invokes only shipped, fixed reproduction code; fetched content is never code input.
            import os
            environment = {key: value for key, value in os.environ.items() if key in {"PATH", "TMPDIR", "SYSTEMROOT", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"}}
            environment["SHAPELOOP_SCOUT_SCRATCH"] = scratch
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
            process = subprocess.Popen([sys.executable, "-m", "shapeloop.scout", "--reproduce", operation], cwd=scratch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if self._cancel.is_set() or (cancel and cancel.is_set()) or time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    return {"success": False, "error": "Reproduction cancelled or timed out", "variants": []}
                time.sleep(0.05)
            output, error = process.communicate()
            if len(output) > 100_000 or len(error) > 100_000:
                return {"success": False, "error": "Reproduction output limit exceeded", "variants": []}
            try:
                result = json.loads(output)
                if isinstance(result, dict):
                    return result
            except ValueError:
                pass
            return {"success": False, "error": f"Reproduction worker exited {process.returncode}", "variants": []}

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        return self.status()

    def start_watch(self) -> dict[str, Any]:
        if self._watch and self._watch.is_alive():
            return self.status()
        self._stop.clear()
        self._watch = threading.Thread(target=self._watch_loop, name="shapeloop-scout-watch", daemon=True)
        self._watch.start()
        return self.status()

    def _watch_loop(self):
        while not self._stop.is_set():
            # A foreground investigation gets the lock first and the watch yields until it is finished.
            if not self._foreground.is_set() and not self._operation_lock.locked():
                try:
                    self.sync(cancel=self._stop)
                except Exception as exc:
                    with self._state_lock:
                        self._state["last_error"] = type(exc).__name__
            self._stop.wait(self.settings.interval_seconds)

    def stop_watch(self) -> dict[str, Any]:
        self._stop.set()
        self._cancel.set()
        if self._watch and self._watch is not threading.current_thread():
            self._watch.join(timeout=0.25)
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return {**self._state, "running": bool(self._watch and self._watch.is_alive()), "stopping": self._stop.is_set(), "network_enabled": self.settings.network_enabled, "sources": list(self.settings.sources), "interval_seconds": self.settings.interval_seconds, "model_budget": self.settings.model_budget, "model_calls": 0, "cached_sources": len(self.store.sources()), "cards": len(self.store.cards())}


def normalize_operation(value: str) -> str:
    text = value.lower()
    for name, words in (("fillet", ("fillet", "chamfer", "圆角", "倒角")), ("selector", ("select", "face", "edge", "选择", "拓扑")), ("step", ("step", "export", "import", "导出", "导入")), ("boolean", ("boolean", "union", "subtract", "intersect", "cut", "布尔")), ("assembly", ("assembly", "clearance", "interference", "装配", "间隙"))):
        if any(word in text for word in words):
            return name
    return "geometry"


def source_score(url: str, operation: str) -> int:
    words = {"fillet": ["test_cadquery", "cq.py", "classreference"], "selector": ["selectors", "test_cadquery"], "step": ["importexport"], "assembly": ["assy"], "boolean": ["cq.py", "test_cadquery"]}.get(operation, ["classreference"])
    return sum(5 for word in words if word in url)


def text_score(content: str, operation: str) -> int:
    words = {"fillet": ["fillet", "radius"], "selector": ["selector", "faces", "edges"], "step": ["export", "importstep", "step"], "boolean": ["union", "cut", "intersect"], "assembly": ["assembly", "constraint"]}.get(operation, ["workplane", "solid"])
    lower = content.lower()
    return sum(min(lower.count(word), 10) for word in words)


def excerpt(content: str, operation: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", "", content, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t]+", " ", text)
    index = text.lower().find({"step": "importstep", "selector": "selector"}.get(operation, operation))
    return text[max(index - 120, 0):max(index - 120, 0) + 900].strip()


def guidance(operation: str) -> tuple[str, str, str, list[str]]:
    if operation == "fillet":
        return ("Resolve a deliberate edge selector, then apply a radius that fits the selected local geometry", "Inspect the selected edge set and local radius bounds; propose a smaller radius explicitly if required. Preserve datums and rerun all hard checks after rebuilding.", "Fixed box variants only: 20×12×8, 24×16×10, 30×18×12 mm; vertical edges; radius 1 mm. No thin walls, cutouts or intersecting fillets.", ["Use an explicitly requested chamfer", "Keep sharp edges and report the kernel limitation"])
    if operation == "selector":
        return ("Use geometric selectors for construction-local intent and validate that the selection is unique", "Re-resolve against current BREP, check cardinality, and reject ambiguity. Persistent semantic identity belongs to feature/datums, not transient face indices.", "Axis-aligned box top planar face and four vertical linear edges across three box dimensions; no general topological naming guarantee.", ["Use an explicit datum and normal/position predicate", "Require the user to clarify an ambiguous reference"])
    if operation == "step":
        return ("Export a BREP STEP and reopen it with CadQuery importStep before trusting interchange", "Compare actual imported solid count, envelope and volume to the built revision; retain semantic source separately because STEP does not reconstruct feature history.", "Three single-solid box variants, STEP roundtrip with envelope/volume consistency; not a proof for every assembly or downstream CAD application.", ["Export parametric source and DesignSpec alongside STEP"])
    if operation == "boolean":
        return ("Use BREP Boolean union/cut/intersect and inspect nonempty valid solids and measured volume", "Isolate operands and operation; reproduce a minimal case, then propose an explicit local repair without silently relaxing tolerance or constraints.", "Three box variants with one central through-cylinder subtraction; no arbitrary coincident/sliver topology guarantee.", ["Change feature ordering as an explicit candidate", "Report unsupported or failing topology"])
    return ("Review current documented API and isolate a minimal geometry problem before changing a candidate", "This lookup supplies relevant source references only; a tailored remedy still needs local reproduction and measured acceptance.", "No local reproduction for this operation; source evidence only.", ["Request a smaller minimal reproduction", "Use explicit structured feature editing"])


def run_reproduction(operation: str) -> dict[str, Any]:
    """Shipped fixed experiments. This function accepts an enum, never source code."""
    import os
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
            resource.setrlimit(resource.RLIMIT_FSIZE, (20_000_000, 20_000_000))
            # Linux address-space limits are meaningful here; macOS native libraries reserve large virtual mappings.
            if sys.platform.startswith("linux"):
                resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
        except (ImportError, ValueError, OSError):
            pass
        import cadquery as cq
        results = []
        for width, depth, height in ((20, 12, 8), (24, 16, 10), (30, 18, 12)):
            model = cq.Workplane("XY").box(width, depth, height)
            result: dict[str, Any] = {"dimensions_mm": [width, depth, height]}
            if operation == "fillet":
                model = model.edges("|Z").fillet(1)
                result["radius_mm"] = 1
            elif operation == "selector":
                result.update(top_faces=model.faces(">Z").size(), vertical_edges=model.edges("|Z").size())
                if result["top_faces"] != 1 or result["vertical_edges"] != 4:
                    raise ValueError("Selector cardinality differs from fixed box expectation")
            elif operation == "step":
                path = Path(os.environ.get("SHAPELOOP_SCOUT_SCRATCH", tempfile.gettempdir())) / f"scout-{width}.step"
                cq.exporters.export(model, str(path))
                reopened = cq.importers.importStep(str(path))
                before, after = model.val(), reopened.val()
                result.update(volume_delta_mm3=abs(before.Volume() - after.Volume()), solid_count=len(after.Solids()))
                if result["volume_delta_mm3"] > 1e-6 or result["solid_count"] != 1:
                    raise ValueError("STEP roundtrip differs")
                model = reopened
            elif operation == "boolean":
                model = model.faces(">Z").workplane().hole(3)
                expected = width * depth * height - 3.141592653589793 * 1.5 ** 2 * height
                result["volume_error_mm3"] = abs(model.val().Volume() - expected)
                if result["volume_error_mm3"] > 1e-6:
                    raise ValueError("Boolean hole volume differs")
            else:
                raise ValueError("Unsupported reproduction operation")
            result.update(valid=model.val().isValid(), solids=len(model.val().Solids()), volume_mm3=model.val().Volume())
            if not result["valid"] or result["solids"] != 1 or result["volume_mm3"] <= 0:
                raise ValueError("Reproduced BREP is invalid or empty")
            results.append(result)
        return {"success": True, "variants": results, "versions": installed_versions(), "method": "Fixed disposable CadQuery BREP experiments; no active design access"}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "variants": []}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--reproduce" and sys.argv[2] in {"fillet", "selector", "step", "boolean"}:
        result = run_reproduction(sys.argv[2])
        print(json.dumps(result))
        raise SystemExit(0 if result["success"] else 1)
    raise SystemExit("Usage: python -m shapeloop.scout --reproduce fillet|selector|step|boolean")

import threading
import time

import httpx
import pytest

from shapeloop.scout import DEFAULT_SOURCES, InvestigationRequest, ScoutSettings, ScoutStore, SolutionScout, validate_source


def scout(tmp_path, handler=None, network=True, versions=None):
    source = DEFAULT_SOURCES[0]
    return SolutionScout(tmp_path / "scout.sqlite", {"network_enabled": network, "sources": [source]}, versions=versions or {"cadquery": "2.6.1"}, transport=httpx.MockTransport(handler or (lambda request: httpx.Response(200, text="Selectors fillet radius faces edges documentation"))))


def test_no_network_has_honest_empty_state(tmp_path):
    app = scout(tmp_path, network=False)
    result = app.ask({"operation": "fillet", "reproduce": False})
    assert result["cards"] == []
    assert "No relevant indexed source" in result["unresolved"][0]
    assert app.sync()["message"].startswith("Network disabled")


def test_real_index_lookup_never_sends_private_design(tmp_path):
    fetched = []
    def handler(request):
        fetched.append(str(request.url))
        assert "private" not in str(request.url)
        return httpx.Response(200, text="fillet radius: use edges on a Workplane")
    app = scout(tmp_path, handler)
    result = app.ask({"operation": "fillet", "error": "private customer file", "geometry": {"private": "design"}, "reproduce": False})
    card = result["cards"][0]
    assert card["status"] == "sourced"
    assert card["source_urls"] == [DEFAULT_SOURCES[0]]
    assert fetched == [DEFAULT_SOURCES[0]]
    assert result["model_calls"] == 0
    assert "deterministic" in result["retrieval_mode"]
    second = app.ask({"operation": "fillet", "reproduce": False})
    assert second["cache_hit"] is True
    assert len(fetched) == 1


def test_reproduction_failure_is_rejected_not_success(tmp_path, monkeypatch):
    app = scout(tmp_path)
    monkeypatch.setattr(app, "_reproduce", lambda *args, **kwargs: {"success": False, "error": "kernel failure", "variants": []})
    card = app.ask({"operation": "fillet"})["cards"][0]
    assert card["status"] == "rejected"
    assert card["promoted"] is False
    assert card["outcome"]["error"] == "kernel failure"


def test_version_and_source_invalidation(tmp_path, monkeypatch):
    app = scout(tmp_path)
    monkeypatch.setattr(app, "_reproduce", lambda *args, **kwargs: {"success": True, "variants": [{}, {}, {}]})
    card = app.ask({"operation": "fillet"})["cards"][0]
    assert card["status"] == "reproduced"
    assert card["promoted"] is True
    app.versions = {"cadquery": "2.7"}
    assert app.cards()[0]["status"] == "stale"
    app.store.cache_source(DEFAULT_SOURCES[0], "changed fillet content")
    assert app.cards()[0]["promoted"] is False


def test_oversized_fetch_bounded_and_not_cached(tmp_path):
    app = scout(tmp_path, lambda request: httpx.Response(200, text="X" * 2048))
    result = app.sync(budget={"max_bytes": 1024, "max_fetches": 1})
    assert result["fetched"] == []
    assert "byte budget" in result["errors"][0]["error"]
    assert app.store.sources() == []


@pytest.mark.parametrize("url", ["http://127.0.0.1/private", "https://localhost/private", "https://cadquery.readthedocs.io.evil.example/en/latest/", "https://raw.githubusercontent.com/CadQuery/cadquery/../../secret", "https://cadquery.readthedocs.io/en/latest/?secret=yes"])
def test_unsafe_source_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_source(url)


def test_redirect_to_private_address_rejected(tmp_path):
    app = scout(tmp_path, lambda request: httpx.Response(302, headers={"location": "https://127.0.0.1/secrets"}))
    result = app.sync()
    assert result["fetched"] == []
    assert "limited" in result["errors"][0]["error"]


def test_scheduler_stop_and_cancellation_preserve_cache(tmp_path):
    app = scout(tmp_path, network=False)
    app.store.cache_source(DEFAULT_SOURCES[0], "fillet radius guidance")
    state = app.start_watch()
    assert state["running"]
    app.stop_watch()
    time.sleep(0.05)
    assert not app.status()["running"]
    assert len(app.store.sources()) == 1
    event = threading.Event()
    event.set()
    app.settings.network_enabled = True
    result = app.sync(cancel=event)
    assert result["cancelled"] is True
    assert len(app.store.sources()) == 1


def test_persistent_library_is_not_active_design(tmp_path):
    app = scout(tmp_path)
    app.ask({"operation": "fillet", "reproduce": False})
    reopened = SolutionScout(ScoutStore(tmp_path / "scout.sqlite"), ScoutSettings(network_enabled=False))
    cards = reopened.cards()
    assert len(cards) == 1
    assert "not been checked" in cards[0]["freshness"]
    assert not (tmp_path / "project.sqlite").exists()


def test_real_fixed_reproductions(tmp_path):
    pytest.importorskip("cadquery")
    app = scout(tmp_path)
    card = app.ask({"operation": "fillet"})["cards"][0]
    assert card["status"] == "reproduced", card["outcome"]
    assert len(card["outcome"]["variants"]) == 3
    assert "No thin walls" in card["applicability"]


def test_sourced_cache_can_be_upgraded_without_refetch(tmp_path,monkeypatch):
    fetched=[]
    app=scout(tmp_path,lambda request:(fetched.append(str(request.url)) or httpx.Response(200,text="fillet radius guidance")))
    app.ask({"operation":"fillet","reproduce":False})
    monkeypatch.setattr(app,"_reproduce",lambda *args,**kwargs:{"success":True,"variants":[{},{},{}]})
    result=app.ask({"operation":"fillet","reproduce":True,"error":"cannot fillet local feature","invariants":["preserve mounting"]})
    assert len(fetched)==1
    assert result["cards"][0]["status"]=="reproduced"
    assert result["cards"][0]["local_context"]["required_invariants"]==["preserve mounting"]

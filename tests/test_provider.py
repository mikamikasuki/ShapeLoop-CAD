import json
import threading

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from shapeloop.provider import DesignContext, EditProposal, ProviderClient, ProviderConfig, ProviderError


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: int


def completion(content, **extra):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], **extra}


def test_missing_provider_is_explicit():
    with pytest.raises(ProviderError, match="require a configured"):
        ProviderClient({}).structured("create", {}, Answer)


def test_model_discovery_key_stays_server_side():
    def handler(request):
        assert request.headers["authorization"] == "Bearer private"
        assert str(request.url) == "https://example.org/v1/models"
        return httpx.Response(200, json={"data": [{"id": "configured-model"}, {"id": "other"}]})
    config = ProviderConfig(endpoint="https://example.org/v1", model="configured-model", api_key="private")
    assert "private" not in json.dumps(config.public())
    assert "private" not in repr(config)
    client = ProviderClient(config, transport=httpx.MockTransport(handler))
    assert client.discover_models() == ["configured-model", "other"]


def test_capability_fallback_and_json_validation():
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "response_format json_schema is unsupported"}})
        return httpx.Response(200, json=completion('{"answer": 42}', usage={"total_tokens": 10}))
    client = ProviderClient({"endpoint": "http://localhost:11434/v1", "model": "my-model"}, transport=httpx.MockTransport(handler))
    assert client.structured("generate answer", {}, Answer).answer == 42
    assert client.output_mode == "json_object"
    assert len(calls) == 2
    assert client.last_call["attempts"] == 2
    assert all(call["stream"] is False for call in calls)


def test_invalid_model_output_has_bounded_retries():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=completion("```python\n__import__('os').system('bad')\n```"))
    client = ProviderClient({"endpoint": "https://example.org/v1", "model": "selected", "max_attempts": 2}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="retry budget exhausted"):
        client.structured("test", {}, Answer)
    assert len(calls) == 2


def test_auth_error_does_not_leak_provider_response_or_secret():
    client = ProviderClient({"endpoint": "https://example.org/v1", "model": "selected", "api_key": "secret"}, transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "secret copied here"}})))
    with pytest.raises(ProviderError) as error:
        client.structured("test", {}, Answer)
    assert "secret" not in str(error.value)


def test_stale_revision_rejected():
    payload = EditProposal(base_revision="other", parameters={"height": 20}).model_dump_json()
    client = ProviderClient({"endpoint": "https://example.org/v1", "model": "selected"}, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completion(payload))))
    with pytest.raises(ProviderError, match="stale"):
        client.edit("reduce height", "current", DesignContext())


def test_unicode_intent_is_sent_without_keyword_router():
    def handler(request):
        prompt = json.loads(request.content)["messages"][1]["content"]
        assert "保留安装孔" in prompt
        return httpx.Response(200, json=completion(EditProposal(base_revision="revision", parameters={"height": 22}, constraints_to_preserve=["mounting"]).model_dump_json()))
    client = ProviderClient({"endpoint": "https://example.org/v1", "model": "selected"}, transport=httpx.MockTransport(handler))
    proposal = client.edit("降低高度，保留安装孔", "revision", {})
    assert proposal.parameters["height"] == 22
    assert proposal.constraints_to_preserve == ["mounting"]


def test_cancelled_does_not_send_request():
    event = threading.Event()
    event.set()
    client = ProviderClient({"endpoint": "https://example.org/v1", "model": "selected"}, transport=httpx.MockTransport(lambda request: pytest.fail("No HTTP when cancelled")))
    with pytest.raises(ProviderError, match="cancelled"):
        client.structured("test", {}, Answer, cancel=event)


def test_insecure_remote_endpoint_rejected():
    with pytest.raises(ValueError, match="HTTPS"):
        ProviderConfig(endpoint="http://remote.example/v1")
    with pytest.raises(ValueError, match="credentials"):
        ProviderConfig(endpoint="https://key@example.org/v1")


def test_output_token_parameter_discovered_with_bounded_fallback():
    calls=[]
    def handler(request):
        payload=json.loads(request.content)
        calls.append(payload)
        if "max_tokens" in payload:
            return httpx.Response(400,json={"error":{"message":"max_tokens is unsupported; use max_completion_tokens"}})
        return httpx.Response(200,json=completion('{"answer": 42}'))
    client=ProviderClient({"endpoint":"https://example.org/v1","model":"selected"},transport=httpx.MockTransport(handler))
    assert client.structured("test",{},Answer).answer==42
    assert len(calls)==2
    assert client.last_call["token_field"]=="max_completion_tokens"


def test_cancellation_during_request_discards_output():
    event=threading.Event()
    def handler(request):
        event.set()
        return httpx.Response(200,json=completion('{"answer":42}'))
    client=ProviderClient({"endpoint":"https://example.org/v1","model":"selected"},transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError,match="cancelled"):
        client.structured("test",{},Answer,cancel=event)

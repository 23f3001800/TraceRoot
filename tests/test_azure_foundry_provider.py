import json
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import AzureFoundryProvider

def test_azure_foundry_uses_model_inference_endpoint_and_json(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"hypotheses": [{"id": "h-1"}]})}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3}}
    captured = {}
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: (captured.update({"args": args, **kwargs}) or Response()))
    provider = AzureFoundryProvider(LLMConfig(), "key", "https://demo.services.ai.azure.com/models", "demo")
    reply = provider.generate("system", [], {}, 5)
    assert reply.decision["hypotheses"][0]["id"] == "H1"
    assert captured["args"][0].endswith("/models/chat/completions")
    assert captured["headers"]["api-key"] == "key"
    assert captured["params"]["api-version"] == "2024-05-01-preview"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_azure_foundry_normalizes_model_role(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "{}"}}]}
    captured = {}
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: (captured.update(kwargs) or Response()))
    AzureFoundryProvider(LLMConfig(), "key", "https://demo.services.ai.azure.com/models", "demo").generate("system", [{"role": "model", "text": "prior"}], {}, 5)
    assert captured["json"]["messages"][1]["role"] == "assistant"


def test_azure_openai_v1_uses_deployment_endpoint(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "{}"}}]}
    captured = {}
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: (captured.update({"args": args, **kwargs}) or Response()))
    AzureFoundryProvider(LLMConfig(), "key", "https://demo.openai.azure.com", "deployment").generate("system", [], {}, 5)
    assert captured["args"][0] == "https://demo.openai.azure.com/openai/v1/chat/completions"
    assert captured["params"] is None
    assert captured["json"]["model"] == "deployment"
    assert captured["json"]["max_completion_tokens"] == LLMConfig().max_tokens
    assert "max_tokens" not in captured["json"]
    assert "temperature" not in captured["json"]
    assert captured["json"]["response_format"]["type"] == "json_schema"

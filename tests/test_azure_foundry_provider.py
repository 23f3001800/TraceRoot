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

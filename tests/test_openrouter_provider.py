import json
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import OpenRouterProvider, load_provider

def test_openrouter_provider_uses_json_and_canonicalizes_ids(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": json.dumps({"hypotheses": [{"id": "h-1"}]})}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}
    captured = {}
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: (captured.update(kwargs) or Response()))
    reply = OpenRouterProvider(LLMConfig(), "key").generate("system", [], {}, 5)
    assert reply.decision["hypotheses"][0]["id"] == "H1"
    assert captured["json"]["response_format"]["type"] == "json_schema"

def test_factory_prefers_openrouter(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=key\n")
    assert isinstance(load_provider(env, LLMConfig()), OpenRouterProvider)


def test_factory_can_select_direct_gemini(tmp_path):
    from traceroot.llms.provider import GeminiProvider
    env = tmp_path / ".env"
    env.write_text("TRACEROOT_PROVIDER=gemini\nGEMINI_API_KEY=key\nOPENROUTER_API_KEY=other\n")
    assert isinstance(load_provider(env, LLMConfig()), GeminiProvider)


def test_factory_can_select_azure_foundry(tmp_path):
    from traceroot.llms.provider import AzureFoundryProvider
    env = tmp_path / ".env"
    env.write_text("TRACEROOT_PROVIDER=azure\nAZURE_FOUNDRY_ENDPOINT=https://demo.services.ai.azure.com/models\nAZURE_FOUNDRY_API_KEY=key\nAZURE_FOUNDRY_MODEL=demo\n")
    assert isinstance(load_provider(env, LLMConfig()), AzureFoundryProvider)


def test_retryable_gemini_failure_uses_openrouter_fallback():
    from traceroot.llms.provider import FallbackProvider, ModelFailure, ModelReply
    class Primary:
        config = LLMConfig()
        def generate(self, *args): raise ModelFailure("provider_error", "temporary", True)
    class Secondary:
        def generate(self, *args): return ModelReply({"ok": True}, {})
    provider = FallbackProvider(Primary(), Secondary())
    assert provider.generate("", [], {}, 1).decision == {"ok": True}
    assert provider.last_failover["from"] == "Primary"

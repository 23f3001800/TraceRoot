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

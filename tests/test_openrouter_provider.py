import json
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import OpenRouterProvider, load_provider

def test_openrouter_provider_uses_json_and_canonicalizes_ids(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": json.dumps({"hypotheses": [{"id": "h-1"}]})}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    reply = OpenRouterProvider(LLMConfig(), "key").generate("system", [], {}, 5)
    assert reply.decision["hypotheses"][0]["id"] == "H1"

def test_factory_prefers_openrouter(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=key\n")
    assert isinstance(load_provider(env, LLMConfig()), OpenRouterProvider)

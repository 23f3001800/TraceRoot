import json
import os
import re
from pathlib import Path
from dataclasses import dataclass, replace
from .config import LLMConfig

class ModelFailure(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message = code, message
        self.retryable = retryable
        super().__init__(message)

@dataclass
class ModelReply:
    decision: dict
    usage: dict

def load_api_key(env_file: Path | None = None) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and env_file and env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "GEMINI_API_KEY":
                key = value.strip()
                if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
                    key = key[1:-1]
                break
    if not key:
        raise ModelFailure("credential_missing", "Configure GEMINI_API_KEY in the environment or operator .env file.")
    return key

def retry_options(config: LLMConfig):
    from google.genai import types
    return types.HttpRetryOptions(
        attempts=1,
        initial_delay=0.5,
        max_delay=0.5,
        exp_base=1,
        jitter=0,
        http_status_codes=[429, 500, 502, 503, 504],
    )

def canonicalize_hypothesis_ids(decision: dict) -> dict:
    """Normalize harmless model formatting while retaining strict stored IDs."""
    hypotheses = decision.get("hypotheses") if isinstance(decision, dict) else None
    if not isinstance(hypotheses, list):
        return decision
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict) or not isinstance(hypothesis.get("id"), str):
            continue
        match = re.fullmatch(r"[Hh][ _-]?([1-9][0-9]?)", hypothesis["id"].strip())
        if match:
            hypothesis["id"] = f"H{match.group(1)}"
    return decision

def generation_schema(schema):
    """Avoid provider grammar expansion; authoritative bounds remain locally enforced."""
    bounds = {'minLength', 'maxLength', 'minItems', 'maxItems', 'minimum', 'maximum', 'pattern', 'maxProperties'}
    if isinstance(schema, dict):
        return {key: generation_schema(value) for key, value in schema.items() if key not in bounds}
    if isinstance(schema, list):
        return [generation_schema(item) for item in schema]
    return schema

class GeminiProvider:
    def __init__(self, config: LLMConfig, api_key: str):
        self.config = config
        self.api_key = api_key

    def generate(self, system: str, messages: list[dict], schema: dict, timeout: float) -> ModelReply:
        from google import genai
        from google.genai import types
        http = types.HttpOptions(
            timeout=max(1, int(timeout * 1000)),
            retry_options=retry_options(self.config),
        )
        try:
            with genai.Client(api_key=self.api_key, http_options=http) as client:
                response = client.models.generate_content(
                    model=self.config.model_name,
                    contents=[types.Content(role=m["role"], parts=[types.Part.from_text(text=m["text"])])
                              for m in messages],
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_json_schema=generation_schema(schema),
                        max_output_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        thinking_config=types.ThinkingConfig(
                            thinking_budget=self.config.thinking_budget, include_thoughts=False),
                    ),
                )
        except Exception as exc:
            code = getattr(exc, "code", None)
            import httpx
            retryable = code in {429, 500, 502, 503, 504} or isinstance(exc, (httpx.TimeoutException, TimeoutError))
            failure_code = "model_timeout" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else "provider_error"
            raise ModelFailure(failure_code, f"Gemini request failed ({code or type(exc).__name__}).", retryable) from None
        candidates = response.candidates or []
        if not candidates or not candidates[0].content:
            raise ModelFailure("empty_response", "Gemini returned no public decision.")
        text = "".join(part.text or "" for part in candidates[0].content.parts or []
                       if not getattr(part, "thought", False))
        try:
            decision = canonicalize_hypothesis_ids(json.loads(text))
        except (ValueError, TypeError):
            raise ModelFailure("invalid_json", "Gemini returned an incomplete or invalid JSON decision.") from None
        usage = response.usage_metadata
        return ModelReply(decision, {
            "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
            "thinking_tokens": getattr(usage, "thoughts_token_count", 0) or 0,
        })

def _env_value(name: str, env_file: Path | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if not value and env_file and env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, separator, candidate = line.partition("=")
            if separator and key.strip() == name:
                value = candidate.strip().strip("\"'")
                break
    return value


class OpenRouterProvider:
    """OpenAI-compatible JSON provider; errors are normalized to ModelFailure."""
    def __init__(self, config: LLMConfig, api_key: str, model_name: str | None = None,
                 base_url: str = "https://openrouter.ai/api/v1"):
        self.model_name = model_name or config.model_name
        self.config = replace(config, model_name=self.model_name)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate(self, system: str, messages: list[dict], schema: dict, timeout: float) -> ModelReply:
        import httpx
        azure_messages = [{"role": "assistant" if message["role"] == "model" else message["role"],
                           "content": message["text"]} for message in messages]
        payload = {"model": self.model_name, "messages": [{"role": "system", "content": system}, *azure_messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "traceroot_decision", "strict": True, "schema": generation_schema(schema)}}}
        try:
            response = httpx.post(f"{self.base_url}/chat/completions", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload, timeout=max(1, timeout))
            response.raise_for_status()
        except (httpx.TimeoutException, TimeoutError):
            raise ModelFailure("model_timeout", "OpenRouter request timed out.", True) from None
        except httpx.HTTPError:
            code = getattr(locals().get("response", None), "status_code", None)
            raise ModelFailure("provider_error", f"OpenRouter request failed ({code or 'response'}).", code in {429, 500, 502, 503, 504}) from None
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            decision = canonicalize_hypothesis_ids(json.loads(content))
        except (KeyError, TypeError, ValueError):
            raise ModelFailure("invalid_json", "OpenRouter returned invalid structured JSON.", True) from None
        usage = body.get("usage") or {}
        return ModelReply(decision, {"input_tokens": usage.get("prompt_tokens", 0) or 0,
            "output_tokens": usage.get("completion_tokens", 0) or 0, "thinking_tokens": 0})


class AzureFoundryProvider:
    """Azure AI Foundry model-inference API using an API key."""
    def __init__(self, config: LLMConfig, api_key: str, endpoint: str, model_name: str,
                 api_version: str = "2024-05-01-preview"):
        self.config = replace(config, model_name=model_name)
        self.api_key, self.endpoint = api_key, endpoint.rstrip("/")
        self.model_name, self.api_version = model_name, api_version
        self.openai_v1 = ".openai.azure.com" in self.endpoint or self.endpoint.endswith("/openai/v1")

    def generate(self, system: str, messages: list[dict], schema: dict, timeout: float) -> ModelReply:
        import httpx
        azure_messages = [{"role": "assistant" if message["role"] == "model" else message["role"],
                           "content": message["text"]} for message in messages]
        payload = {"model": self.model_name, "messages": [{"role": "system", "content": system}, *azure_messages],
            "temperature": self.config.temperature, "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"}}
        url = f"{self.endpoint}/chat/completions"
        params = {"api-version": self.api_version}
        if self.openai_v1:
            base = self.endpoint if self.endpoint.endswith("/openai/v1") else f"{self.endpoint}/openai/v1"
            url, params = f"{base}/chat/completions", None
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            payload.pop("temperature")
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "traceroot_decision", "strict": True, "schema": generation_schema(schema)}}
        try:
            response = httpx.post(url, headers={"api-key": self.api_key, "Content-Type": "application/json"},
                params=params, json=payload, timeout=max(1, timeout))
            response.raise_for_status()
        except (httpx.TimeoutException, TimeoutError):
            raise ModelFailure("model_timeout", "Azure Foundry request timed out.", True) from None
        except httpx.HTTPError:
            code = getattr(locals().get("response", None), "status_code", None)
            raise ModelFailure("provider_error", f"Azure Foundry request failed ({code or 'response'}).",
                               code in {408, 429, 500, 502, 503, 504}) from None
        try:
            body = response.json(); content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            decision = canonicalize_hypothesis_ids(json.loads(content))
        except (KeyError, TypeError, ValueError):
            raise ModelFailure("invalid_json", "Azure Foundry returned invalid JSON.", True) from None
        usage = body.get("usage") or {}
        return ModelReply(decision, {"input_tokens": usage.get("prompt_tokens", 0) or 0,
            "output_tokens": usage.get("completion_tokens", 0) or 0, "thinking_tokens": 0})


class FallbackProvider:
    """Use a second configured provider only after a retryable primary failure."""
    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.config = primary.config
        self.last_failover = None

    def generate(self, system: str, messages: list[dict], schema: dict, timeout: float) -> ModelReply:
        self.last_failover = None
        try:
            return self.primary.generate(system, messages, schema, timeout)
        except ModelFailure as failure:
            if not failure.retryable:
                raise
            self.last_failover = {"code": failure.code, "message": failure.message,
                                  "from": type(self.primary).__name__, "to": type(self.fallback).__name__}
            return self.fallback.generate(system, messages, schema, timeout)


def load_provider(env_file: Path | None, config: LLMConfig):
    selected = _env_value("TRACEROOT_PROVIDER", env_file).casefold()
    if selected not in {"", "gemini", "openrouter", "azure", "fallback"}:
        raise ModelFailure("provider_invalid", "TRACEROOT_PROVIDER must be gemini, openrouter, azure, or fallback.")
    azure_key = _env_value("AZURE_FOUNDRY_API_KEY", env_file) or _env_value("AZURE_AI_FOUNDRY_API_KEY", env_file)
    azure_endpoint = _env_value("AZURE_FOUNDRY_ENDPOINT", env_file) or _env_value("AZURE_AI_FOUNDRY_ENDPOINT", env_file)
    azure_model = _env_value("AZURE_FOUNDRY_MODEL", env_file) or _env_value("AZURE_AI_FOUNDRY_MODEL", env_file)
    azure = AzureFoundryProvider(config, azure_key, azure_endpoint, azure_model,
        _env_value("AZURE_FOUNDRY_API_VERSION", env_file) or "2024-05-01-preview") if azure_key and azure_endpoint and azure_model else None
    if selected == "azure":
        if not azure:
            raise ModelFailure("credential_missing", "Configure AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY, and AZURE_FOUNDRY_MODEL.")
        return azure
    router_key = _env_value("OPENROUTER_API_KEY", env_file)
    router = OpenRouterProvider(config, router_key, _env_value("OPENROUTER_MODEL", env_file) or "google/gemini-2.5-flash",
                                _env_value("OPENROUTER_BASE_URL", env_file) or "https://openrouter.ai/api/v1") if router_key else None
    if selected == "openrouter":
        if not router:
            raise ModelFailure("credential_missing", "Configure OPENROUTER_API_KEY for OpenRouter.")
        return router
    if not selected and router and not _env_value("GEMINI_API_KEY", env_file):
        return router
    gemini = GeminiProvider(config, load_api_key(env_file))
    if selected == "fallback" or (not selected and (router or azure)):
        if azure:
            return FallbackProvider(gemini, azure)
        return FallbackProvider(gemini, router)
    return gemini

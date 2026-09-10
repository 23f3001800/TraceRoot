import json
import os
from pathlib import Path
from dataclasses import dataclass
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
            decision = json.loads(text)
        except (ValueError, TypeError):
            raise ModelFailure("invalid_json", "Gemini returned an incomplete or invalid JSON decision.") from None
        usage = response.usage_metadata
        return ModelReply(decision, {
            "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
            "thinking_tokens": getattr(usage, "thoughts_token_count", 0) or 0,
        })

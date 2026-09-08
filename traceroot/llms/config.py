from dataclasses import dataclass

@dataclass(frozen=True)
class LLMConfig:
    model_name: str = "gemini-3.6-flash"
    max_tokens: int = 4096
    temperature: float = 0.2
    thinking_budget: int = 1024
    max_transient_retries: int = 1

    def __post_init__(self):
        if not 256 <= self.max_tokens <= 8192:
            raise ValueError("max_tokens must be between 256 and 8192")
        if not 0 <= self.temperature <= 1 or not 0 <= self.thinking_budget <= 2048:
            raise ValueError("Invalid sampling or thinking budget")
        if type(self.max_transient_retries) is not int or not 0 <= self.max_transient_retries <= 1:
            raise ValueError("max_transient_retries must be 0 or 1")

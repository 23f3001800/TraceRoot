from dataclasses import dataclass

@dataclass(frozen=True)
class LLMConfig:
    model_name: str = "gemini-2.5-flash"
    max_tokens: int = 4096
    temperature: float = 0.2
    thinking_budget: int = 1024

    def __post_init__(self):
        if not 256 <= self.max_tokens <= 8192:
            raise ValueError("max_tokens must be between 256 and 8192")
        if not 0 <= self.temperature <= 1 or not 0 <= self.thinking_budget <= 2048:
            raise ValueError("Invalid sampling or thinking budget")

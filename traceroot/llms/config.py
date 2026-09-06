from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """
    Configuration for a Language Model (LLM).
    """

    model_name: str = Field(..., description="The name of the language model.")
    max_tokens: int = Field(..., description="The maximum number of tokens to generate.")
    temperature: float = Field(..., description="Sampling temperature for generation.")
    top_p: float = Field(..., description="Top-p sampling parameter.")
    frequency_penalty: float = Field(..., description="Frequency penalty for generation.")
    presence_penalty: float = Field(..., description="Presence penalty for generation.")


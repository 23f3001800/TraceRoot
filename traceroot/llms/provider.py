from google import genai
from openai import OpenAI

class LLMProvider:
    def __init__(self, provider: str = "gemini"):
        self.provider = provider.lower()
        if self.provider == "gemini":
            self.client = genai.Client()
        elif self.provider == "openrouter":
            self.client = OpenAI()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def generate_content(self, model: str, contents: list):
        if self.provider == "gemini":
            return self.client.models.generate_content(model=model, contents=contents)
        elif self.provider == "openrouter":
            # Assuming OpenRouter has a similar method for generating content
            return self.client.chat.completions.create(model=model, messages=contents)
    def get_model_info(self, model: str):
        if self.provider == "gemini":
            return self.client.models.get(model=model)
        elif self.provider == "openrouter":
            # Assuming OpenRouter has a method to get model info
            return self.client.models.retrieve(model=model)
    def stream_content(self, model: str, contents: list):
        if self.provider == "gemini":
            return self.client.models.stream_content(model=model, contents=contents)
        elif self.provider == "openrouter":
            # Assuming OpenRouter has a method to stream content
            return self.client.chat.completions.stream(model=model, messages=contents)
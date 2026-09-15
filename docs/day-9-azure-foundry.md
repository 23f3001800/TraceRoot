# Day 9 - Azure Foundry provider

## Change

TraceRoot can now select Azure AI Foundry through its model-inference REST API.

Set these local-only values in .env:

    TRACEROOT_PROVIDER=azure
    AZURE_FOUNDRY_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/models
    AZURE_FOUNDRY_API_KEY=YOUR_KEY
    AZURE_FOUNDRY_MODEL=YOUR_DEPLOYED_MODEL
    AZURE_FOUNDRY_API_VERSION=2024-05-01-preview

The provider sends read-only investigator prompts to /chat/completions, uses the api-key header, and requests JSON output. No target-app or database write capability is added.

Azure OpenAI deployments are also supported: point AZURE_FOUNDRY_ENDPOINT at the Azure OpenAI resource endpoint and set AZURE_FOUNDRY_MODEL to its deployment name. TraceRoot then uses its /openai/v1/chat/completions endpoint.

## Fallback

TRACEROOT_PROVIDER=fallback uses Gemini first, then Azure Foundry when Azure configuration is complete. OpenRouter remains available through TRACEROOT_PROVIDER=openrouter.

## Verification

- Azure endpoint, key header, API version, JSON response request, and result parsing have unit coverage.
- A live resume requires the three local Azure values above. They were absent from the current environment when this change was made.

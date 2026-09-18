# Incident workspace UI

The incident workspace is a simple browser-native interface with a ChatGPT-style conversation center and a coding-agent-style activity timeline.

## Inputs

The intake form accepts:

- repository path or URL (required)
- incident report (required)
- reproduction command (optional)
- runtime or environment context (optional)

Saving an incident stores only the declared inputs. It does not execute a model, tool, provider call, target command, or write action.

## Frontend layout

The UI is deliberately split into modules:

- `ui/workspace/index.html` defines structure and accessible labels.
- `ui/workspace/styles/base.css` defines tokens and base rules.
- `ui/workspace/styles/layout.css` defines the three-column workspace.
- `ui/workspace/styles/components.css` defines form and button components.
- `ui/workspace/src/api.js` owns HTTP and SSE transport.
- `ui/workspace/src/renderer.js` renders bounded semantic events.
- `ui/workspace/src/main.js` wires user actions.

All workspace source files use ASCII-only UI text and CSS shapes, avoiding encoding-dependent symbols.

## Activity visibility

SSE exposes concise events such as stage changes, agent starts, tool results, provider failures, and audit outcomes. The interface never displays private reasoning, sensitive prompts, or secrets.

## Workspace form-reset correction

Incident saving completed before the browser tried to reset the form through an expired async event reference. The handler now captures the form before awaiting the API result, then resets that saved reference.

Verification: workspace UI and frontend regression tests passed, 3 tests total.

import argparse
import json
from pathlib import Path
import sys
from .context import Context
from .contracts import ToolFailure, ToolResult, ToolError
from .docker_runtime import cleanup, prepare
from .tools import TOOLS

def main():
    parser = argparse.ArgumentParser(description="TraceRoot operator CLI and six investigation tools")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare", help="Operator-only disposable environment setup")
    setup.add_argument("--repository", type=Path, required=True)
    setup.add_argument("--sessions", type=Path, default=Path(".traceroot-runs"))
    setup.add_argument("--docker", required=True, help="Trusted Docker CLI executable path")
    invoke = commands.add_parser("call")
    invoke.add_argument("--session", type=Path, required=True)
    invoke.add_argument("tool", choices=TOOLS)
    inputs = invoke.add_mutually_exclusive_group()
    inputs.add_argument("--input", default="{}", help="JSON object of documented tool inputs")
    inputs.add_argument("--input-file", type=Path, help="Operator-provided JSON input file")
    destroy = commands.add_parser("cleanup", help="Operator-only disposable environment cleanup")
    destroy.add_argument("--session", type=Path, required=True)

    investigator = commands.add_parser("investigate", help="Run one bounded Gemini investigator")
    investigator.add_argument("--session", type=Path, required=True)
    investigator.add_argument("--task-file", type=Path, required=True)
    investigator.add_argument("--env-file", type=Path, default=Path(".env"))
    investigator.add_argument("--max-tool-calls", type=int, default=15)
    investigator.add_argument("--max-seconds", type=int, default=300)
    investigator.add_argument("--model-timeout", type=int, default=60)
    investigator.add_argument("--max-model-calls", type=int, default=30)
    resume = commands.add_parser("resume", help="Resume a checkpoint with its original cumulative budgets")
    resume.add_argument("--session", type=Path, required=True)
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--env-file", type=Path, default=Path(".env"))
    resume.add_argument("--retry-invalid", action="store_true", help="Retry a finished invalid-decision checkpoint after a contract update.")
    commands.add_parser("tool-schemas", help="Print the six model-facing tool contracts")
    approval_ui = commands.add_parser("approval-ui", help="Serve a loopback-only exact-patch approval page")
    approval_ui.add_argument("--session", type=Path, required=True)
    approval_ui.add_argument("--patch-file", type=Path, required=True)
    approval_ui.add_argument("--investigation-id", required=True)
    approval_ui.add_argument("--port", type=int, default=8765)
    workspace_ui = commands.add_parser("workspace-ui", help="Serve the loopback-only incident reporting workspace")
    workspace_ui.add_argument("--workspace-dir", type=Path, default=Path(".traceroot-workspace"))
    workspace_ui.add_argument("--port", type=int, default=8875)
    args = parser.parse_args()
    try:

        if args.command == "approval-ui":
            from .approval_ui import serve_approval
            serve_approval(Context.load(args.session), args.patch_file, args.investigation_id, args.port)
            return 0
        if args.command == "workspace-ui":
            from .workspace_ui import serve_workspace
            serve_workspace(args.workspace_dir.resolve(), args.port)
            return 0
        if args.command == "tool-schemas":
            from .agents.schemas import CATALOG
            print(json.dumps(CATALOG, indent=2))
            return 0
        if args.command in {"investigate", "resume"}:
            from .agents.langgraph import investigate_graph
            from .agents.investigator import Budget
            from .llms.config import LLMConfig
            from .llms.provider import ModelFailure, load_provider
            try:
                provider = load_provider(args.env_file, LLMConfig())
                result = investigate_graph(
                    Context.load(args.session),
                    json.loads(args.task_file.read_text()) if args.command == "investigate" else None, provider,
                    Budget(args.max_tool_calls, args.max_seconds, args.model_timeout, args.max_model_calls) if args.command == "investigate" else Budget(),
                    progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True),
                    resume_run_id=args.run_id if args.command == "resume" else None,
                    retry_invalid=args.retry_invalid if args.command == "resume" else False,
                )
            except ModelFailure as exc:
                print(json.dumps({"status": "MODEL_PROVIDER_FAILURE", "error": {"code": exc.code, "message": exc.message}}))
                return 2
            print(json.dumps(result, indent=2))
            return 0 if result["final"]["status"] == "ROOT_CAUSE_SUPPORTED" else 1
        if args.command == "prepare":
            ctx = prepare(args.repository, args.sessions.resolve(), args.docker)
            result = ToolResult("ok", {"session": str(ctx.session_dir), "repository": ctx.repository.source,
                                      "snapshot_id": ctx.repository.snapshot_id, "log_source": "application"})
        elif args.command == "cleanup":
            cleanup(Context.load(args.session))
            result = ToolResult("ok", {"cleaned_up": True})
        else:
            ctx = Context.load(args.session)
            payload = json.loads(args.input_file.read_text() if args.input_file else args.input)
            if not isinstance(payload, dict) or "context" in payload:
                raise ToolFailure("invalid_input", "Tool input must be a JSON object without context overrides.")
            result = TOOLS[args.tool](ctx, **payload)
            evidence = args.session / "evidence"
            evidence.mkdir(exist_ok=True)
            (evidence / f"{result.metadata['run_id']}.json").write_text(json.dumps({
                "input": payload, "result": result.to_dict()}, indent=2))
        print(json.dumps(result.to_dict(), indent=2))
        # A successfully observed failing test is a successful tool call.
        return 0 if result.status == "ok" else 2
    except ToolFailure as exc:
        print(json.dumps(ToolResult(exc.status, error=ToolError(exc.code, exc.message)).to_dict(), indent=2))
        return 2
    except (OSError, ValueError):
        print(json.dumps(ToolResult("error", error=ToolError("operator_error", "Invalid input or unavailable session.")).to_dict()))
        return 2

if __name__ == "__main__":
    sys.exit(main())

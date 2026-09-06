import ast
import configparser
import re
import shlex
import tomllib
from .contracts import ToolFailure
from .repository import relative_path

def configuration(repo) -> tuple[list[str], set[str]]:
    roots, markers = ["tests"], set()
    if "pytest.ini" in repo.manifest:
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(repo.read("pytest.ini"))
        if config.has_section("pytest"):
            roots = shlex.split(config.get("pytest", "testpaths", fallback="tests"))
            marker_text = config.get("pytest", "markers", fallback="")
            markers = {line.strip().split(":")[0].split("(")[0]
                       for line in marker_text.splitlines() if line.strip()}
    elif "pyproject.toml" in repo.manifest:
        config = tomllib.loads(repo.read("pyproject.toml")).get("tool", {}).get("pytest", {}).get("ini_options", {})
        roots = config.get("testpaths", ["tests"])
        markers = {m.split(":")[0].strip() for m in config.get("markers", [])}
    if not isinstance(roots, list) or not roots:
        raise ToolFailure("invalid_test_configuration", "Public testpaths must be a nonempty list.")
    for root in roots:
        if relative_path(root) != "tests" and not relative_path(root).startswith("tests/"):
            raise ToolFailure("test_path_denied", "Only public tests/ paths are supported.")
    return roots, markers

def discover(repo) -> list[dict]:
    roots, configured_markers = configuration(repo)
    tests = []
    for path in sorted(repo.manifest):
        if not (path.endswith(".py") and any(path.startswith(root + "/") for root in roots)):
            continue
        if not path.rsplit("/", 1)[-1].startswith("test_"):
            continue
        tree = ast.parse(repo.read(path))
        def collect(nodes, parents=()):
            for node in nodes:
                if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    collect(node.body, (*parents, node.name))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    markers = []
                    for decorator in node.decorator_list:
                        target = decorator.func if isinstance(decorator, ast.Call) else decorator
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute):
                            if target.value.attr == "mark":
                                markers.append(target.attr)
                    tests.append({"node_id": "::".join((path, *parents, node.name)),
                                  "name": node.name, "markers": markers})
        collect(tree.body)
    return tests

def select(repo, selector: str | None, marker: str | None = None) -> list[str]:
    tests = discover(repo)
    if not tests:
        raise ToolFailure("no_tests", "No public tests were discovered.", "unavailable")
    if selector is None:
        args = configuration(repo)[0]
    elif not isinstance(selector, str):
        raise ToolFailure("invalid_selector", "Test selector must be a string.")
    elif any(test["node_id"] == selector for test in tests):
        args = [selector]
    elif selector in {test["node_id"].split("::")[0] for test in tests}:
        args = [selector]
    else:
        matches = [test["node_id"] for test in tests if test["name"] == selector]
        if len(matches) != 1:
            raise ToolFailure("invalid_selector", "Selector must identify one public test or test file.")
        args = matches
    if marker is not None:
        known = configuration(repo)[1] | {m for test in tests for m in test["markers"]}
        if not isinstance(marker, str):
            raise ToolFailure("invalid_marker", "Invalid marker filter.")
        tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[()]", marker)
        if "".join(tokens) != re.sub(r"\s", "", marker) or not tokens:
            raise ToolFailure("invalid_marker", "Use a bounded pytest marker expression.")
        if len(marker) > 100 or any(t not in known | {"and", "or", "not", "(", ")"} for t in tokens):
            raise ToolFailure("invalid_marker", "Marker filter contains an unknown marker.")
        args += ["-m", marker]
    return args

def reproduction_args(repo, command: list[str] | None) -> tuple[list[str], str]:
    if command is not None:
        if not isinstance(command, list) or not all(isinstance(v, str) for v in command):
            raise ToolFailure("command_denied", "Reproduction commands must be argv arrays, not shell strings.")
        args = list(command)
        if args[:3] == ["python", "-m", "pytest"]:
            args = args[3:]
        elif args[:1] == ["pytest"]:
            args = args[1:]
        else:
            raise ToolFailure("command_denied", "Version 1 supports approved pytest commands only.")
        selector, marker = None, None
        while args:
            arg = args.pop(0)
            if arg == "-q":
                continue
            if arg == "-m" and args and marker is None:
                marker = args.pop(0)
            elif not arg.startswith("-") and selector is None:
                selector = arg
            else:
                raise ToolFailure("command_denied", "Unsupported reproduction argument.")
        return select(repo, selector, marker), "Supplied public pytest command."
    candidates = [test for test in discover(repo)
                  if {"reproduction", "regression"} & set(test["markers"])]
    if len(candidates) != 1:
        code = "reproduction_unavailable" if not candidates else "reproduction_ambiguous"
        raise ToolFailure(code, "No unique public reproduction/regression test; provide an approved command.", "unavailable")
    return [candidates[0]["node_id"]], "Selected the unique public reproduction/regression-marked test."

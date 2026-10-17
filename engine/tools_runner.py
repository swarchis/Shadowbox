"""Runs coach-written Python tools in a sandbox, and screens tool code before it can join a toolbox.

Sandbox: a separate isolated Python process (-I), empty environment, temp working dir, timeout.
On macOS it additionally runs under sandbox-exec with network and out-of-tempdir writes denied.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

ALLOWED_IMPORTS = {"re", "math", "itertools", "collections", "string", "functools", "dataclasses", "typing", "json", "textwrap"}
# bare names that must never be called / referenced (attribute access like re.compile is fine)
BANNED_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars", "getattr", "setattr", "delattr"}
# module-like names that can't be imported anyway (imports are allowlisted) but could be reached via attributes
BANNED_NAMES = {"os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins", "ctypes", "pickle",
                "codecs", "marshal", "inspect", "gc", "multiprocessing", "threading"}
BANNED_ATTRS = BANNED_NAMES | {"open", "eval", "exec", "popen", "system", "spawn", "getattr", "setattr", "delattr",
                               "globals", "locals", "vars", "modules", "import_module", "load_module"}
MAX_LINES = 150

_WRAPPER = r"""
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("tool", "tool.py")
mod = importlib.util.module_from_spec(spec)
data = json.loads(sys.stdin.read())
try:
    spec.loader.exec_module(mod)
    out = mod.run(data["spec"], data["verilog"], data["ports"])
    if not isinstance(out, dict):
        raise TypeError("run() must return a dict")
    res = {"fired": bool(out.get("fired")), "findings": [str(f)[:300] for f in (out.get("findings") or [])][:10]}
except Exception as e:
    res = {"fired": False, "findings": [], "error": f"{type(e).__name__}: {e}"[:300]}
print("SBX_TOOL_RESULT " + json.dumps(res))
"""


def screen_tool_code(code: str) -> list[str]:
    """Static guard. Returns a list of problems (empty = acceptable)."""
    problems = []
    if len(code.splitlines()) > MAX_LINES:
        problems.append(f"tool is longer than {MAX_LINES} lines")
    if re.search(r"Prob\d{3}", code):
        problems.append("tool hardcodes a problem id")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error: {e}"]
    has_run = any(isinstance(n, ast.FunctionDef) and n.name == "run" and len(n.args.args) == 3 for n in tree.body)
    if not has_run:
        problems.append("missing top-level `def run(spec, verilog, ports)`")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"import of {a.name} not allowed")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"import from {node.module} not allowed")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            problems.append(f"call to {node.func.id}() not allowed")
        elif isinstance(node, ast.Name) and (node.id in BANNED_NAMES or node.id in BANNED_CALLS or node.id.startswith("__")):
            problems.append(f"use of {node.id} not allowed")
        elif isinstance(node, ast.Attribute) and (node.attr.startswith("__") or node.attr in BANNED_ATTRS):
            problems.append(f"attribute {node.attr} not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            problems.append("dunder strings not allowed")
    return sorted(set(problems))


def _python() -> str:
    """The base interpreter (outside the project's venv), so the sandbox can deny the whole project folder."""
    base = getattr(sys, "_base_executable", None) or sys.executable
    return base if Path(base).exists() else sys.executable


def _sandbox_prefix(workdir: Path) -> list[str]:
    """macOS sandbox: no network, no writes outside the temp dir, and no reads of the project folder
    (reference designs, held-out data, run results) or of the user's home folder."""
    exe = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or not exe:
        return []
    real = workdir.resolve()
    deny_reads = {config.ROOT.resolve(), Path.home().resolve(), Path(config.RUNS_DIR).resolve(), Path(config.VERSIONS_DIR).resolve()}
    deny = "".join(f'(deny file-read* (subpath "{d}"))' for d in sorted(map(str, deny_reads)))
    profile = (
        "(version 1)(allow default)(deny network*)(deny file-write*)"
        f"{deny}"
        f'(allow file-read* file-write* (subpath "{real}") (literal "/dev/null"))'
    )
    return [exe, "-p", profile]


def run_tool(code: str, spec: str, verilog: str, ports: list[dict], timeout: int = config.TOOL_TIMEOUT_S) -> dict:
    """Returns {"fired": bool, "findings": [...], "error": optional str}."""
    with tempfile.TemporaryDirectory(prefix="sbx_tool_") as tmp:
        tmpd = Path(tmp)
        (tmpd / "tool.py").write_text(code)
        (tmpd / "wrapper.py").write_text(_WRAPPER)
        cmd = [*_sandbox_prefix(tmpd), _python(), "-I", "-S", "wrapper.py"]
        payload = json.dumps({"spec": spec, "verilog": verilog, "ports": ports})
        try:
            proc = subprocess.run(cmd, input=payload, capture_output=True, text=True, cwd=tmpd, timeout=timeout, env={})
        except subprocess.TimeoutExpired:
            return {"fired": False, "findings": [], "error": "tool timed out"}
    if proc.returncode in (-2, -15):  # the tool was killed by Ctrl-C/SIGTERM aimed at us: not the tool's fault
        raise KeyboardInterrupt
    for line in proc.stdout.splitlines():
        if line.startswith("SBX_TOOL_RESULT "):
            return json.loads(line[len("SBX_TOOL_RESULT "):])
    return {"fired": False, "findings": [], "error": (proc.stderr or "tool produced no result")[-300:]}


def run_toolbox(pb, spec: str, verilog: str, ports: list[dict]) -> list[dict]:
    """Run every tool in a playbook on one draft."""
    reports = []
    for name in pb.tools:
        res = run_tool(pb.tool_sources[name], spec, verilog, ports)
        reports.append({"tool": name, **res})
    return reports

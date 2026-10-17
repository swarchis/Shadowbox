"""Central configuration. Every tunable lives here; override via environment variables."""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DATASET_DIR = DATA_DIR / "raw" / "verilog-eval" / "dataset_spec-to-rtl"
SPLITS_PATH = DATA_DIR / "splits.json"


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from ROOT/.env into the environment. Real environment variables win.
    Tests set SHADOWBOX_NO_DOTENV=1 so a real key never leaks into them."""
    if os.environ.get("SHADOWBOX_NO_DOTENV") == "1" or not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / ".env")


def _find_iverilog_bin() -> Path:
    local = ROOT / ".tools" / "iv" / "bin"
    if (local / "iverilog").exists():
        return local
    found = shutil.which("iverilog")
    if found:
        return Path(found).parent
    return local  # harness raises a clear error if missing


IVERILOG_BIN = _find_iverilog_bin()
IVERILOG_FLAGS = ["-Wall", "-Winfloop", "-Wno-timescale", "-g2012"]  # same as VerilogEval's Makefile
SIM_TIMEOUT_S = 30
COMPILE_TIMEOUT_S = 30

# ---------------------------------------------------------------- LLM provider
CRUSOE_BASE_URL = os.environ.get("CRUSOE_BASE_URL", "https://api.inference.crusoecloud.com/v1")
CRUSOE_API_KEY = os.environ.get("CRUSOE_API_KEY", "")
# Mock mode runs the whole system offline with fake (but well-formed) model output.
# It is ON automatically when no API key is set, and can be forced with SHADOWBOX_MOCK=1.
MOCK = os.environ.get("SHADOWBOX_MOCK", "") == "1" or not CRUSOE_API_KEY

# Mock and real runs never share output folders, so fake numbers can't leak into the demo.
_suffix = "_mock" if MOCK else ""
VERSIONS_DIR = Path(os.environ.get("SHADOWBOX_VERSIONS_DIR", ROOT / f"versions{_suffix}"))
RUNS_DIR = Path(os.environ.get("SHADOWBOX_RUNS_DIR", ROOT / f"runs{_suffix}"))
# Cost ledger location. None = RUNS_DIR/ledger.jsonl. The ablation pins it to the main run's ledger
# while it switches RUNS_DIR, so the spend cap always covers all spending.
LEDGER_PATH: Path | None = None

# Nemotron reasoning control. "off" asks the model to skip long thinking (faster, cheaper).
# Verify the effect with `python -m engine.cli smoke`; set to "on" if quality drops.
WORKER_THINKING = os.environ.get("SHADOWBOX_WORKER_THINKING", "off")
# "low" = Nemotron's low_effort reasoning: about half the thinking time of "on" with similar answers (measured).
COACH_THINKING = os.environ.get("SHADOWBOX_COACH_THINKING", "low")

# Model IDs: verify against the Crusoe console before a real run.
# Model IDs and prices from Crusoe's hackathon skill file (crusoe-developer-hub, refreshed Oct 13 2026).
# `python -m engine.cli check` verifies every ID against /v1/models. Rate limits are per model, so
# spreading roles across models (worker vs judge) also spreads the load.
MODELS = {
    "worker": os.environ.get("SHADOWBOX_WORKER_MODEL", "nvidia/Nemotron-3.5-Lightning-30B-A3B"),
    "coach": os.environ.get("SHADOWBOX_COACH_MODEL", "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"),
    "judge": os.environ.get("SHADOWBOX_JUDGE_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    # "ultra" = the big-model comparison. Nemotron 3 Ultra isn't offered to this key, so the biggest listed
    # Nemotron (3 Super, 120B, 4x the worker) stands in.
    "ultra": os.environ.get("SHADOWBOX_ULTRA_MODEL", "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"),
    "transfer": os.environ.get("SHADOWBOX_TRANSFER_MODEL", "google/gemma-4-31b-it"),
}

# USD per 1M tokens (input, output), from Crusoe's pricing page via the skill file.
PRICES = {  # exact IDs and prices from Crusoe's /v1/models for this key
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.05, 0.20),
    "nvidia/Nemotron-3.5-Lightning-30B-A3B": (0.05, 0.20),
    "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B": (0.30, 2.40),
    "nvidia/NVIDIA-Nemotron-3.5-Super-VL": (0.10, 0.40),
    "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B": (0.30, 1.83),
    "google/gemma-4-31b-it": (0.14, 0.40),
    "openai/gpt-oss-120b": (0.05, 0.25),
    "deepseek-ai/Deepseek-V4-Flash": (0.14, 0.28),
    "deepseek-ai/DeepSeek-V4.1-Flash": (0.29, 1.20),
    "deepseek-ai/DeepSeek-V4-Pro": (1.74, 3.48),
    "zai-org/GLM-5.3-Flash": (0.15, 0.50),
    "zai-org/GLM-5.3": (1.40, 4.40),
    "Qwen/Qwen3.8-27B": (0.25, 2.00),
}
DEFAULT_PRICE = (1.00, 3.20)  # unknown models are billed at the worst case

SPEND_CAP_USD = float(os.environ.get("SHADOWBOX_SPEND_CAP", "45"))
LLM_CONCURRENCY = int(os.environ.get("SHADOWBOX_CONCURRENCY", "8"))
LLM_MAX_RETRIES = int(os.environ.get("SHADOWBOX_LLM_RETRIES", "9"))  # backoff 1,2,4..60 s: ~4 min before an item counts as an API error
# Crusoe limits each model to 600 requests/min with a payment method on file (30 without one).
# Requests are throttled client-side below this so bursts don't turn into 429s.
RPM_PER_MODEL = int(os.environ.get("SHADOWBOX_RPM", "500"))
LLM_TIMEOUT_S = 180
COACH_TIMEOUT_S = 420  # coach replies are long and reasoned; a timeout there costs a whole round

# Reasoning models spend part of max_tokens on thinking, so these are generous. A reply cut off at
# the limit (finish_reason "length") is retried once with double the limit.
MAX_TOKENS = {
    "planner": 4096,
    "writer": 6144,
    "debugger": 6144,
    "attacker": 3072,
    "multi_attacker": 4096,
    "judge": 4096,
    "coach": 16384,
}
MAX_TOKENS_CEILING = 32768
# With reasoning on, thinking shares the reply budget (measured ~4.4k tokens per Builder call), so allow more.
THINKING_MAX_TOKENS = 16384
BREAKER_THINKING = os.environ.get("SHADOWBOX_BREAKER_THINKING", "off")  # fast exploration runs; set "low" for the final run
# Exploration runs keep the Builder's reasoning off so improvements must come from learned tools, memory and rules.
# The final demo run sets SHADOWBOX_ALLOW_THINK=1 so the team may also learn to turn reasoning on, on top of that.
ALLOW_THINK = os.environ.get("SHADOWBOX_ALLOW_THINK", "0") == "1"
# Staged runs: reasoning becomes an allowed change only from this round on (0 = never, unless ALLOW_THINK).
THINK_AFTER_ROUND = int(os.environ.get("SHADOWBOX_THINK_AFTER_ROUND", "0"))


def think_allowed(round_no: int | None) -> bool:
    return ALLOW_THINK or (THINK_AFTER_ROUND > 0 and round_no is not None and round_no >= THINK_AFTER_ROUND)
# Only long-form roles get the bigger-budget retry. A cut-off Breaker or Judge reply is a runaway
# (e.g. a wide value spelled out bit by bit), not a budget problem: their parsers handle it instead.
TRUNCATION_RETRY_ROLES = ("planner", "coach")  # a Builder reply past its limit is a ramble: the debugger fixes it
# The held-out baselines that run alongside self-play get their own, smaller lane so they never starve the loop.
BASELINE_CONCURRENCY = int(os.environ.get("SHADOWBOX_BASELINE_CONCURRENCY", "6"))

# ---------------------------------------------------------------- experiment
SPLIT_SEED = 1234
SPLIT_SIZES = {"train": 30, "val": 30}  # remainder (92) is the held-out test
WORK_TEMPERATURE = float(os.environ.get("SHADOWBOX_WORK_TEMP", "0.0"))
DRAFT_TEMPERATURE = 0.7
LLM_SEED = 7  # sent when the provider supports it

GATE_MARGIN = 3  # net problems flipped required to accept a change...
CLEAN_WIN_MIN = 2  # ...or a clean win: fixes at least this many and breaks none (held-out stays the final judge)
CANDIDATES_PER_ROUND = int(os.environ.get("SHADOWBOX_K", "1"))
TOOLBOX_CAP = 6
TOOL_MIN_PROBLEMS = 3
TOOL_TIMEOUT_S = 10

BUG_POOL_EXTRA_DRAFTS = 2  # extra temp-0.7 v0 drafts per val problem to enlarge the pool
BUG_POOL_MAX = 50
STIMULUS_MAX_CYCLES = 200
RANDOM_STIMULUS_CYCLES = 120

TEST_TIME_DRAFTS = int(os.environ.get("SHADOWBOX_DRAFTS", "3"))  # 3 keeps the (thinking) final exam short
FINAL_RUNS = 3

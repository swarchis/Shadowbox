"""The team's memory: verified solutions from its own past, retrieved for similar new problems.

Learning from history, Version N+1 style: every training problem the Builder solved correctly (official test
passed and no Breaker bug) can be added to the playbook's memory. For a new problem the Builder is shown the most
similar remembered problems (spec + verified code). Retrieval is plain TF-IDF cosine similarity over the specs,
so it is deterministic, cheap and needs no extra model. Only training problems ever enter memory.
"""
from __future__ import annotations

import math
import re
from collections import Counter

MEMORY_CAP = 80
MIN_SIMILARITY = 0.12

_STOP = set("""a an and are as at be by for from has have i if in into is it its of on or that the then this to
was when which will with you your module named topmodule interface following implement input inputs output outputs
port ports bit bits one unless otherwise specified like would should""".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9_]+|\d+", text.lower()) if t not in _STOP and len(t) > 1]


def retrieve(spec: str, memory: list[dict], k: int) -> list[dict]:
    """The k remembered problems most similar to this spec (cosine over TF-IDF), above a minimum similarity."""
    if not memory or k <= 0:
        return []
    docs = [Counter(_tokens(m["spec"])) for m in memory]
    n = len(docs)
    df = Counter(t for d in docs for t in d)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}

    def vec(c: Counter) -> dict:
        return {t: f * idf.get(t, math.log(n + 1)) for t, f in c.items()}

    def cos(a: dict, b: dict) -> float:
        dot = sum(v * b.get(t, 0.0) for t, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    q = vec(Counter(_tokens(spec)))
    scored = sorted(((cos(q, vec(d)), i) for i, d in enumerate(docs)), reverse=True)
    return [dict(memory[i], similarity=round(s, 3)) for s, i in scored[:k] if s >= MIN_SIMILARITY]


def memory_block(spec: str, memory: list[dict], k: int) -> str:
    hits = retrieve(spec, memory, k)
    if not hits:
        return ""
    parts = [f"### Similar problem (solved and verified correct by your team)\n{h['spec'][:900]}\n"
             f"Verified solution:\n```verilog\n{h['code']}```" for h in hits]
    return ("\n\nYour team's memory: problems similar to this one that you solved correctly before. Reuse what "
            "applies, but implement THIS specification exactly.\n\n" + "\n\n".join(parts))


def verified_from_match(match: dict, known: set[str]) -> list[dict]:
    """Training problems solved correctly this round (official pass, no Breaker bug), not yet in memory."""
    out = []
    for r in match.get("problems", []):
        if r["official"].get("passed") and r.get("hard_pass") and r["build"].get("code") and r["problem_id"] not in known:
            out.append({"problem_id": r["problem_id"], "spec": r["spec"], "code": r["build"]["code"], "round": match.get("round")})
    return out

"""The team's memory of verified solutions: retrieval, prompt injection, gating, and a full loop."""
import asyncio

import pytest

from engine import coach, config, dataset, llm, loop, memory, playbook, store
from engine.builder import build


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "VERSIONS_DIR", tmp_path / "versions")
    monkeypatch.setattr(config, "LEDGER_PATH", None)
    monkeypatch.setattr(config, "MOCK", True)
    monkeypatch.setattr(llm, "LEDGER", llm.Ledger())
    yield


def _entry(pid):
    p = dataset.load_problems()[pid]
    return {"problem_id": pid, "spec": p.spec, "code": dataset.ref_source(p).replace("RefModule", "TopModule"), "round": 1}


def test_retrieval_finds_the_same_family():
    P = dataset.load_problems()
    mem = [_entry(pid) for pid in ("Prob050_kmap1", "Prob031_dff", "Prob030_popcount255", "Prob014_andgate")]
    hits = memory.retrieve(P["Prob057_kmap2"].spec, mem, 2)
    assert hits and hits[0]["problem_id"] == "Prob050_kmap1"
    hits = memory.retrieve(P["Prob034_dff8"].spec, mem, 1)
    assert hits and hits[0]["problem_id"] == "Prob031_dff"
    assert memory.retrieve(P["Prob057_kmap2"].spec, [], 2) == []


def test_memory_reaches_the_builder_prompt():
    playbook.ensure_v0()
    pb = playbook.load("builder", 0).clone()
    assert pb.params["think"] == "low" and pb.params["memory_k"] == 0  # thinking is part of the baseline now
    pb.memory = [_entry("Prob050_kmap1")]
    pb.params["memory_k"] = 2
    seen = []

    class Spy(llm.LLMClient):
        async def chat(self, **kw):
            seen.append(kw["messages"][1]["content"])
            return await super().chat(**kw)

    asyncio.run(build(dataset.load_problems()["Prob057_kmap2"], pb, Spy(mock=True)))
    assert "Your team's memory" in seen[0] and "Prob050" not in seen[0][:50]
    assert "Verified solution" in seen[0]


def test_memory_add_is_a_gated_change_and_dedupes():
    playbook.ensure_v0()
    pb = playbook.load("builder", 0)
    cand, err = coach.apply(pb, {"change_type": "memory_add", "entries": [_entry("Prob050_kmap1")]}, [], "c")
    assert err is None and len(cand.memory) == 1 and cand.params["memory_k"] == 2
    assert cand.fingerprint() != pb.fingerprint()  # memory changes the playbook, so caches can't go stale
    _, err = coach.apply(cand, {"change_type": "memory_add", "entries": [_entry("Prob050_kmap1")]}, [], "c")
    assert err and "no new" in err


def test_verified_from_match_only_takes_clean_passes():
    m = {"round": 2, "problems": [
        {"problem_id": "A", "spec": "s", "official": {"passed": True}, "hard_pass": True, "build": {"code": "module"}},
        {"problem_id": "B", "spec": "s", "official": {"passed": True}, "hard_pass": False, "build": {"code": "module"}},
        {"problem_id": "C", "spec": "s", "official": {"passed": False}, "hard_pass": False, "build": {"code": "module"}},
    ]}
    assert [e["problem_id"] for e in memory.verified_from_match(m, set())] == ["A"]
    assert memory.verified_from_match(m, {"A"}) == []


def test_loop_proposes_memory_and_persists_it(monkeypatch):
    monkeypatch.setattr(config, "GATE_MARGIN", -99)  # accept everything so the test sees memory get promoted
    ctx = asyncio.run(loop.run_loop(rounds=1, minutes=None, k=1, train_limit=6, val_limit=4, llm=llm.LLMClient(mock=True)))
    lineage = playbook.read_lineage()
    mem = [e for e in lineage if e["change_type"] == "memory_add"]
    assert mem and mem[0]["source"] == "memory"
    cur = playbook.load_current("builder")
    if mem[0]["accepted"]:
        assert cur.memory and all(m["problem_id"] in dataset.load_splits()["train"] for m in cur.memory)
    assert ctx.train  # ran

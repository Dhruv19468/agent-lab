"""The scorer: deterministic metrics, quote checking and the formula, with a fake judge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.judge import Judge
from app.evaluation.scorer import combine, load_reference, score_plan, score_structure
from app.evaluation.text import overlap_f1, quote_found
from app.runtime.dataset import find_project
from tests.fakes import FakeLLM, reply

REFERENCE = {
    "objectives": "Verify extraction of tiers with page references.",
    "nfr_performance": "Supplier-year calculation within 2 minutes.",
}
BRD = "Performance: Calculation for one supplier-year within 2 minutes. Approval above USD 50,000."
CANDIDATE = """# Master Test Plan – Demo
## 1. Test Objectives
Verify extraction of tiers and rates with page references for every agreement.
## 10. Performance and Scalability
Calculate one supplier-year within 2 minutes under normal load.
Finance Manager approval above USD 75,000.
"""


def judge_script(request):
    system = request["messages"][0]["content"]
    if "answer key" in system:
        points = [
            {"section": "objectives", "point": "Tier extraction", "quote": "Verify extraction of tiers"},
            {"section": "nfr_performance", "point": "2-minute calc", "quote": "within 2 minutes"},
            {"section": "objectives", "point": "Invented", "quote": "this sentence is not in the reference"},
        ]
        return reply(json.dumps({"points": points}))
    if "required points" in system:
        results = [
            {"id": 1, "covered": True, "quote": "Verify extraction of tiers and rates"},
            {"id": 2, "covered": True, "quote": "a quote the plan never contains at all"},  # made up
        ]
        return reply(json.dumps({"results": results}))
    claims = [
        {
            "claim": "2 min",
            "plan_quote": "one supplier-year within 2 minutes",
            "support": "brd",
            "brd_quote": "supplier-year within 2 minutes",
        },
        {
            "claim": "75k",
            "plan_quote": "Finance Manager approval above USD 75,000",
            "support": "brd",
            "brd_quote": "Approval above USD 75,000",
        },  # not in the BRD: must become 'none'
        {"claim": "ghost", "plan_quote": "text that is not in the plan", "support": "none", "brd_quote": ""},
    ]
    return reply(json.dumps({"claims": claims}))


async def test_score_plan_verifies_every_quote(tmp_path: Path) -> None:
    llm = FakeLLM(judge_script)
    result = await score_plan(
        judge=Judge(llm=llm, deployment="judge"),
        project="P06",
        candidate=CANDIDATE,
        reference=REFERENCE,
        brd_text=BRD,
        diagrams=[],
        cache_dir=tmp_path,
    )
    counts = result.details["counts"]
    assert counts["points"] == 2  # the reference point with a made-up quote was dropped
    assert counts["covered"] == 1 and result.coverage == 0.5  # the made-up candidate quote doesn't count
    assert counts["claims"] == 2 and counts["supported"] == 1  # ghost claim dropped, USD 75,000 unsupported
    assert result.faithfulness == 0.5
    assert result.structure == pytest.approx(2 / 20)
    assert result.overall == pytest.approx(round(combine(0.1, 0.5, result.similarity, 0.5), 4))
    assert all(request["json_output"] and request["temperature"] == 0 for request in llm.requests)

    # the reference points are cached: a second scoring doesn't ask for them again
    llm.requests.clear()
    await score_plan(
        judge=Judge(llm=llm, deployment="judge"),
        project="P06",
        candidate=CANDIDATE,
        reference=REFERENCE,
        brd_text=BRD,
        diagrams=[],
        cache_dir=tmp_path,
    )
    assert len(llm.requests) == 2 and len(list(tmp_path.glob("P06_points_*.json"))) == 1


def test_formula() -> None:
    assert combine(1, 1, 1, 1) == pytest.approx(1.0)
    assert combine(1, 1, 1, 0.5) == pytest.approx(0.5)
    assert combine(0.8, 0.5, 0.4, 1) == pytest.approx(0.25 * 0.8 + 0.45 * 0.5 + 0.30 * 0.4)


def test_structure_needs_real_content() -> None:
    score, present = score_structure({"objectives": "short", "risks": "x" * 60})
    assert present["risks"] and not present["objectives"]
    assert score == pytest.approx(1 / 20)


def test_quote_found() -> None:
    document = "Retroactive: spend USD 2.1M with tiers 2% ≥USD 1M and 3% ≥USD 2M → USD 63,000."
    assert quote_found("**spend USD 2.1M** with tiers", document)
    assert quote_found("spend USD 2.1M with tier 2% >=USD 1M and 3%", document)  # one letter off
    assert not quote_found("spend EUR 9.9M with no tiers whatsoever here", document)
    assert not quote_found("USD", document)  # too short to prove anything


def test_overlap_f1() -> None:
    assert overlap_f1("same words here", "same words here") == pytest.approx(1.0)
    assert overlap_f1("apples", "oranges") == 0.0
    assert overlap_f1("", "anything") == 0.0


def test_reference_prefers_gold(data_root: Path) -> None:
    project = find_project(data_root, "p06")
    sections, source = load_reference(data_root, project)
    assert source == "gold" and sections == {"objectives": "Verify tiers."}

    project.gold = None
    sections, source = load_reference(data_root, project)
    assert source == "testplan" and "nfr_reliability" in sections


async def test_points_are_extracted_in_batches_with_a_retry(tmp_path: Path) -> None:
    """One request per few sections, and an empty section is asked again on its own."""
    from app.evaluation.judge import extract_points

    reference = {f"s{i}": f"Section {i} must verify feature number {i} with its own rule text here." for i in range(6)}
    calls: list[str] = []

    def script(request):
        body = request["messages"][1]["content"]
        calls.append(body)
        keys = body.split("(keys: ")[1].split(")")[0].split(", ")
        # first time, the judge "forgets" s1; when asked alone it answers
        points = [
            {"section": key, "point": f"Feature {key}", "quote": f"must verify feature number {key[1:]}"}
            for key in keys
            if not (key == "s1" and len(keys) > 1)
        ]
        return reply(json.dumps({"points": points}))

    points = await extract_points(Judge(llm=FakeLLM(script), deployment="judge"), "P00", reference, tmp_path)
    assert [point["section"] for point in points] == ["s0", "s1", "s2", "s3", "s4", "s5"]
    assert len(calls) == 3  # sections 0-3, sections 4-5, then s1 alone

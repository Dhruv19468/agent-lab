"""The two LLM-judged metrics: coverage and faithfulness.

Rule for every judgement: the judge must quote the text it relied on, and the quote is
checked in code (text.quote_found). A judgement whose quote isn't really there is thrown
away, so the judge can't invent support.

Coverage
  1. extract: the judge reads the REFERENCE plan and lists its checkable points, each with a
     quote from the reference. Cached per project in data/_cache/, so every run of every
     prompt version is checked against exactly the same list (a fair comparison).
  2. check: for each point, is it in the CANDIDATE plan? Covered only with a verified quote.

Faithfulness
  The judge lists the candidate plan's project-specific claims (numbers, systems, roles,
  rules) and finds each one in the BRD (verified quote) or the architecture diagram.
  Claims with no support are made up: faithfulness = supported / all claims.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.evaluation.sections import SECTIONS
from app.evaluation.text import normalise, quote_found
from app.integrations.azure_openai import LlmError, ModelReply
from app.runtime.storage import Storage, as_storage

logger = logging.getLogger("platform.evaluation")

MAX_POINTS_PER_SECTION = 6
MIN_POINTS_PER_SECTION = 2
SECTIONS_PER_REQUEST = 4  # small batches: one request for the whole plan made the judge stop after a few points
MIN_SECTION_CHARS_FOR_POINTS = 30  # a heading alone (or a few words) yields nothing to check
MAX_CLAIMS = 30
JUDGE_MAX_TOKENS = 8000


class JudgeModel(Protocol):
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        deployment: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_output: bool = False,
    ) -> ModelReply: ...


@dataclass
class TokenCount:
    prompt: int = 0
    completion: int = 0


@dataclass
class Judge:
    llm: JudgeModel
    deployment: str
    tokens: TokenCount = field(default_factory=TokenCount)

    async def ask_json(self, system: str, content: str | list[dict[str, Any]]) -> dict[str, Any]:
        reply = await self.llm.chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            deployment=self.deployment,
            temperature=0,
            max_tokens=JUDGE_MAX_TOKENS,
            json_output=True,
        )
        self.tokens.prompt += reply.prompt_tokens
        self.tokens.completion += reply.completion_tokens
        try:
            data = json.loads(reply.content or "{}")
        except json.JSONDecodeError as error:
            raise LlmError(
                f"The judge did not return valid JSON (finish_reason={reply.finish_reason})."
            ) from error
        if not isinstance(data, dict):
            raise LlmError("The judge returned JSON that is not an object.")
        return data


# --- coverage -----------------------------------------------------------------------------

EXTRACT_SYSTEM = f"""You are a senior QA reviewer preparing an answer key.
You get some sections of a REFERENCE master test plan written by an expert. For EVERY section
given, list the points a good test plan for this project must contain: concrete, checkable
items such as a scenario to test, a threshold or number, a system or integration, a role rule,
a criterion, a risk and its mitigation. Skip generic filler that any plan would say.

Rules:
- Every section with real content gets between {MIN_POINTS_PER_SECTION} and {MAX_POINTS_PER_SECTION} points (1 is fine for a
  section of one or two lines). Do not skip a section and do not merge sections.
- "point": one short sentence in your own words.
- "quote": the exact words from that reference section that state it (copy them, 5-25 words).
- "section": the section key exactly as given in the heading "### <key>".

Answer with JSON only: {{"points": [{{"section": "<key>", "point": "...", "quote": "..."}}]}}"""

CHECK_SYSTEM = """You are a strict QA reviewer. You get a numbered list of required points and a
CANDIDATE test plan. For each point decide whether the candidate plan covers it: the same
thing must be stated or clearly tested (same meaning; different wording is fine; a vaguer
or partial mention that misses the specific number, rule or system does NOT count).

For a covered point, "quote" must be copied exactly from the CANDIDATE plan (5-30 words).
For an uncovered point, "quote" is "".

Answer with JSON only: {"results": [{"id": <number>, "covered": true|false, "quote": "..."}]}"""


def _cache_name(project: str, reference: dict[str, str], deployment: str) -> str:
    digest = hashlib.sha256(
        json.dumps({"reference": reference, "judge": deployment, "v": 2}, sort_keys=True).encode()
    ).hexdigest()[:16]
    return f"{project}_points_{digest}.json"


def _accept_points(
    data: dict[str, Any], reference: dict[str, str], wanted: list[str], per_section: dict[str, int], stats: dict[str, int]
) -> list[dict[str, str]]:
    """The judge's points for the `wanted` sections whose quote really is in that section."""
    accepted = []
    for item in data.get("points") or []:
        if not isinstance(item, dict):
            continue
        section, point, quote = (str(item.get("section", "")), str(item.get("point", "")), str(item.get("quote", "")))
        if section not in wanted or not point.strip():
            continue
        if not quote_found(quote, reference[section]):
            stats["dropped"] += 1
            logger.info("Dropped a reference point whose quote isn't in section %s: %r", section, quote[:80])
            continue
        if per_section.get(section, 0) >= MAX_POINTS_PER_SECTION:
            continue
        per_section[section] = per_section.get(section, 0) + 1
        accepted.append({"section": section, "point": point.strip(), "quote": quote.strip()})
    return accepted


def _batch_body(reference: dict[str, str], keys: list[str]) -> str:
    sections = "\n\n".join(f"### {key} ({SECTIONS.get(key, (key,))[0]})\n{reference[key]}" for key in keys)
    return f"REFERENCE TEST PLAN SECTIONS (keys: {', '.join(keys)})\n\n{sections}"


async def extract_points(
    judge: Judge,
    project: str,
    reference: dict[str, str],
    cache_dir: Storage | Path | None,
    cache_prefix: str = "",
) -> list[dict[str, str]]:
    """The reference plan's checkable points, each with a verified quote. Cached on disk.

    Asked SECTIONS_PER_REQUEST sections at a time, and a section that comes back empty is asked
    again on its own: with the whole plan in one request the judge returned only a handful of
    points, which made coverage a coin toss (e.g. "4 of 5").
    """
    store = as_storage(cache_dir) if cache_dir is not None else None
    cache = f"{cache_prefix.strip('/')}/" if cache_prefix.strip("/") else ""
    cache += _cache_name(project, reference, judge.deployment)
    if store is not None and store.is_file(cache):
        return json.loads(store.read_bytes(cache).decode("utf-8"))

    keys = [key for key, text in reference.items() if len(text.strip()) >= MIN_SECTION_CHARS_FOR_POINTS]
    points: list[dict[str, str]] = []
    per_section: dict[str, int] = {}
    stats = {"dropped": 0}
    for start in range(0, len(keys), SECTIONS_PER_REQUEST):
        batch = keys[start : start + SECTIONS_PER_REQUEST]
        data = await judge.ask_json(EXTRACT_SYSTEM, _batch_body(reference, batch))
        points += _accept_points(data, reference, batch, per_section, stats)

    for key in [key for key in keys if not per_section.get(key)]:  # second chance, alone
        data = await judge.ask_json(EXTRACT_SYSTEM, _batch_body(reference, [key]))
        points += _accept_points(data, reference, [key], per_section, stats)

    order = {key: index for index, key in enumerate(reference)}
    points.sort(key=lambda point: order.get(point["section"], 99))
    logger.info(
        "Reference points for %s: %d from %d sections (%d dropped: quote not found)",
        project, len(points), len(keys), stats["dropped"],
    )
    if store is not None and points:
        store.write_bytes(cache, json.dumps(points, indent=2, ensure_ascii=False).encode("utf-8"), overwrite=True)
    return points


async def check_coverage(judge: Judge, points: list[dict[str, str]], candidate: str) -> list[dict[str, Any]]:
    """Each point + covered (only if the judge's quote is really in the candidate plan)."""
    if not points:
        return []
    numbered = "\n".join(f"{index}. [{p['section']}] {p['point']}" for index, p in enumerate(points, start=1))
    data = await judge.ask_json(
        CHECK_SYSTEM, f"REQUIRED POINTS\n{numbered}\n\nCANDIDATE TEST PLAN\n\n{candidate}"
    )
    verdicts = {}
    for item in data.get("results") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            verdicts[item["id"]] = item

    normalised_candidate = normalise(candidate)
    results = []
    for index, point in enumerate(points, start=1):
        verdict = verdicts.get(index, {})
        quote = str(verdict.get("quote") or "")
        claimed = bool(verdict.get("covered"))
        verified = claimed and quote_found(quote, candidate, normalised_document=normalised_candidate)
        results.append(
            {
                **point,
                "covered": verified,
                "candidateQuote": quote if claimed else "",
                "note": "quote not found in the plan; not counted" if claimed and not verified else "",
            }
        )
    return results


# --- faithfulness -------------------------------------------------------------------------

FAITH_SYSTEM = f"""You are a strict fact-checker for test plans. You get the source BRD (and,
when attached, the architecture diagram) and a CANDIDATE test plan written from them.

List up to {MAX_CLAIMS} project-specific factual claims the candidate plan makes: numbers,
thresholds, volumes, time limits, named systems and integrations, roles and their rights,
business rules, in/out-of-scope items, dates and phases. Prefer the claims that matter most.
Do NOT list generic testing practice (e.g. "use boundary-value analysis", "log defects in Jira"
is generic unless the BRD names Jira) or statements the plan marks as an assumption or TBD.

For each claim:
- "plan_quote": exact words from the CANDIDATE plan stating the claim (5-30 words).
- "support": "brd" if the BRD states it, "diagram" if only the architecture diagram shows it,
  "none" if neither supports it or it contradicts them.
- "brd_quote": when support is "brd", the exact BRD words that support it (5-30 words), else "".

Answer with JSON only:
{{"claims": [{{"claim": "...", "plan_quote": "...", "support": "brd|diagram|none", "brd_quote": "..."}}]}}"""


async def check_faithfulness(
    judge: Judge, brd_text: str, candidate: str, diagram_data_urls: list[str]
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"SOURCE BRD\n\n{brd_text}\n\nCANDIDATE TEST PLAN\n\n{candidate}"}
    ]
    for url in diagram_data_urls:
        content.append({"type": "text", "text": "Architecture diagram from the project:"})
        content.append({"type": "image_url", "image_url": {"url": url}})
    data = await judge.ask_json(FAITH_SYSTEM, content if diagram_data_urls else content[0]["text"])

    normalised_candidate, normalised_brd = normalise(candidate), normalise(brd_text)
    claims = []
    for item in (data.get("claims") or [])[:MAX_CLAIMS]:
        if not isinstance(item, dict):
            continue
        plan_quote = str(item.get("plan_quote") or "")
        if not quote_found(plan_quote, candidate, normalised_document=normalised_candidate):
            continue  # the judge misquoted the plan: not a real claim of this plan
        support = str(item.get("support") or "none").lower()
        brd_quote = str(item.get("brd_quote") or "")
        if support == "brd" and not quote_found(brd_quote, brd_text, normalised_document=normalised_brd):
            support, note = "none", "BRD quote not found in the BRD"
        elif support == "diagram" and not diagram_data_urls:
            support, note = "none", "no diagram was available"
        else:
            note = ""
        if support not in {"brd", "diagram"}:
            support = "none"
        claims.append(
            {
                "claim": str(item.get("claim") or ""),
                "planQuote": plan_quote,
                "support": support,
                "brdQuote": brd_quote if support == "brd" else "",
                "note": note,
            }
        )
    return claims

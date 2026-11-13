"""Small text helpers shared by the scorer: normalising, quote checks, word-overlap F1."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

_TRANSLATE = str.maketrans(
    {"–": "-", "—": "-", "‑": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "≥": ">=", "≤": "<=", " ": " "}
)
_MARKUP = re.compile(r"[*_`#|>]+")
_SPACES = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*%?")

STOPWORDS = set(
    """a an and are as at be by can for from has have in into is it its of on or that the their this to
    was were will with within must should shall all any each per via not no than then these those""".split()
)


def normalise(text: str) -> str:
    """Lower case, plain dashes and quotes, no Markdown symbols, single spaces."""
    text = (text or "").translate(_TRANSLATE).lower()
    text = _MARKUP.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def quote_found(quote: str, document: str, *, normalised_document: str | None = None) -> bool:
    """Is `quote` really in `document`? Exact after normalising, or a 90% near-match for long quotes.

    Every judgement the LLM makes must point at text that exists; a quote that isn't there
    means the judge made it up, and the judgement is discarded.
    """
    needle = normalise(quote).strip(" .\"'")
    if len(needle) < 4:
        return False
    haystack = normalised_document if normalised_document is not None else normalise(document)
    if needle in haystack:
        return True
    if len(needle) < 25:
        return False
    matcher = SequenceMatcher(None, haystack, needle, autojunk=False)
    match = matcher.find_longest_match(0, len(haystack), 0, len(needle))
    if match.size >= 0.9 * len(needle) and all(
        number
        in _NUMBER.findall(haystack[max(0, match.a - match.b) : max(0, match.a - match.b) + len(needle) + 3])
        for number in _NUMBER.findall(needle)
    ):
        return True
    # Small differences spread through the quote (a changed word): compare the aligned window.
    # A near-match must still have the same numbers: "USD 75,000" is not "USD 50,000".
    start = max(0, match.a - match.b)
    needle_numbers = _NUMBER.findall(needle)
    for extra in range(-3, 4):
        window = haystack[max(0, start - 3) : start + len(needle) + extra]
        if SequenceMatcher(None, window, needle, autojunk=False).ratio() >= 0.9 and all(
            number in _NUMBER.findall(window) for number in needle_numbers
        ):
            return True
    return False


def words(text: str) -> list[str]:
    return [word for word in _WORD.findall(normalise(text)) if word not in STOPWORDS]


def overlap_f1(candidate: str, reference: str) -> float:
    """Word-overlap F1 (bag of words, stopwords removed): 1.0 = same words, 0.0 = nothing shared."""
    cand, ref = Counter(words(candidate)), Counter(words(reference))
    if not cand or not ref:
        return 0.0
    common = sum((cand & ref).values())
    if common == 0:
        return 0.0
    precision = common / sum(cand.values())
    recall = common / sum(ref.values())
    return 2 * precision * recall / (precision + recall)

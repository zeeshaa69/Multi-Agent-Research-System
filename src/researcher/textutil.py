"""Deterministic text helpers used by extraction and fact checking.

These are intentionally simple, inspectable heuristics (tokenisation, light
stemming, number and negation detection). They never generate new text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_WORD = re.compile(r"[A-Za-z0-9]+(?:[.,'][A-Za-z0-9]+)*")

STOPWORDS = frozenset(
    """
    a an the and or but if then else of to in on at by for with from as is are was were be
    been being it its this that these those there here which who whom whose what when where
    why how do does did done has have had having will would shall should can could may might
    must not no nor so than too very also into over under about after before during between
    through per via their them they he she his her we our you your i me my us one some any
    each other such more most many much both all only own same just still yet
    """.split()
)

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "hundred": 100,
}
MULTIPLIERS = {"thousand": 1e3, "million": 1e6, "billion": 1e9}

NEGATIONS = frozenset(
    {
        "not",
        "no",
        "never",
        "without",
        "cannot",
        "neither",
        "nor",
        "none",
        "isn't",
        "doesn't",
        "don't",
        "wasn't",
        "weren't",
        "didn't",
        "won't",
        "hasn't",
        "haven't",
        "aren't",
    }
)
HEDGES = frozenset(
    {
        "may",
        "might",
        "could",
        "possibly",
        "perhaps",
        "reportedly",
        "allegedly",
        "suggest",
        "suggests",
        "suggested",
        "appears",
        "unconfirmed",
        "unclear",
        "speculated",
        "rumored",
        "probably",
        "presumably",
    }
)

_ABBREVIATIONS = ("e.g", "i.e", "vs", "dr", "mr", "mrs", "ms", "st", "fig", "approx", "etc")
_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])|\n+")


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def words(text: str) -> list[str]:
    return [m.group(0) for m in _WORD.finditer(text)]


def stem(word: str) -> str:
    w = word.lower()
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith(("sses", "xes", "zes", "ches", "shes")):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    for suffix in ("ing", "ed"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)]
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def _is_numeric_token(tok: str) -> bool:
    t = tok.lower()
    return t[0].isdigit() or t in NUMBER_WORDS or t in MULTIPLIERS


def content_tokens(text: str) -> set[str]:
    """Stemmed non-stopword, non-numeric tokens."""
    out: set[str] = set()
    for tok in words(text):
        low = tok.lower()
        if low in STOPWORDS or _is_numeric_token(tok):
            continue
        out.add(stem(low))
    return out


def numbers(text: str) -> set[float]:
    """Numeric values mentioned in the text, with thousand/million/billion applied."""
    toks = [t.lower() for t in words(text)]
    found: set[float] = set()
    for i, tok in enumerate(toks):
        value: float | None = None
        if tok[0].isdigit():
            try:
                value = float(tok.replace(",", ""))
            except ValueError:
                value = None
        elif tok in NUMBER_WORDS:
            value = float(NUMBER_WORDS[tok])
        if value is None:
            continue
        if i + 1 < len(toks) and toks[i + 1] in MULTIPLIERS:
            value *= MULTIPLIERS[toks[i + 1]]
        found.add(value)
    return found


def number_units(text: str) -> dict[str, set[float]]:
    """Numeric values grouped by the word that follows them (their unit), e.g. 'megawatt'.

    Numbers with no unit word (``in 2021``) are grouped under the empty string.
    """
    toks = [t.lower() for t in words(text)]
    out: dict[str, set[float]] = {}
    for i, tok in enumerate(toks):
        value: float | None = None
        if tok[0].isdigit():
            try:
                value = float(tok.replace(",", ""))
            except ValueError:
                value = None
        elif tok in NUMBER_WORDS:
            value = float(NUMBER_WORDS[tok])
        if value is None:
            continue
        j = i + 1
        if j < len(toks) and toks[j] in MULTIPLIERS:
            value *= MULTIPLIERS[toks[j]]
            j += 1
        unit = ""
        if j < len(toks) and toks[j] not in STOPWORDS and not _is_numeric_token(toks[j]):
            unit = stem(toks[j])
        out.setdefault(unit, set()).add(value)
    return out


def format_number(value: float) -> str:
    if value >= 1e9:
        return f"{value / 1e9:g} billion"
    if value >= 1e6:
        return f"{value / 1e6:g} million"
    return f"{value:g}"


def has_negation(text: str) -> bool:
    return any(w.lower() in NEGATIONS for w in words(text))


def is_hedged(text: str) -> bool:
    return any(w.lower() in HEDGES for w in words(text))


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


def split_sentences(text: str) -> list[Span]:
    """Split into sentences, keeping character offsets into the original text."""
    spans: list[Span] = []

    def add(start: int, end: int) -> None:
        chunk = text[start:end]
        stripped = chunk.strip()
        if stripped:
            lead = len(chunk) - len(chunk.lstrip())
            spans.append(Span(start + lead, start + lead + len(stripped), stripped))

    start = 0
    for m in _BOUNDARY.finditer(text):
        before = text[start : m.start()].lower().rstrip(".").split(" ")[-1]
        if before in _ABBREVIATIONS and "\n" not in m.group(0):
            continue
        add(start, m.start())
        start = m.end()
    add(start, len(text))
    return spans


def overlap_coefficient(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def locate_quote(quote: str, text: str) -> Literal["exact", "fuzzy", "none"]:
    """Check that a quote really occurs in a source text.

    ``exact``: identical after whitespace normalisation.
    ``fuzzy``: same word sequence ignoring case and punctuation.
    ``none``: not found.
    """
    if not quote.strip():
        return "none"
    if normalize_ws(quote) in normalize_ws(text):
        return "exact"
    q = [w.lower() for w in words(quote)]
    t = [w.lower() for w in words(text)]
    if q and any(t[i : i + len(q)] == q for i in range(len(t) - len(q) + 1) if t[i] == q[0]):
        return "fuzzy"
    return "none"

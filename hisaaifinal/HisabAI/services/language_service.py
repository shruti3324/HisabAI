"""Indian multilingual speech normalization used before AI extraction.

This intentionally normalizes number *language*, not business facts. The
transaction service remains the only place that derives outstanding balances.
"""
from __future__ import annotations
import re


# Common Hindi, Marathi, Hinglish and English number vocabulary. This is a
# vocabulary/grammar, not a list of sentence templates, so natural phrasing and
# code-switching are supported.
UNITS = {
    "zero": 0, "shunya": 0, "ek": 1, "one": 1, "do": 2, "don": 2, "donhi": 2,
    "two": 2, "teen": 3, "tin": 3, "three": 3, "char": 4, "chaar": 4,
    "four": 4, "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "che": 6,
    "saha": 6, "six": 6, "saat": 7, "sat": 7, "seven": 7, "aath": 8,
    "aat": 8, "eight": 8, "nau": 9, "nav": 9, "nine": 9, "das": 10,
    "daha": 10, "ten": 10, "gyarah": 11, "akra": 11, "eleven": 11,
    "barah": 12, "bara": 12, "twelve": 12, "terah": 13, "tera": 13,
    "thirteen": 13, "chaudah": 14, "chauda": 14, "fourteen": 14,
    "pandrah": 15, "pandhara": 15, "fifteen": 15, "solah": 16, "sola": 16,
    "sixteen": 16, "satrah": 17, "satra": 17, "seventeen": 17,
    "atharah": 18, "athra": 18, "eighteen": 18, "unnis": 19, "ekonis": 19,
    "nineteen": 19, "bees": 20, "vis": 20, "twenty": 20,
    "tees": 30, "tis": 30, "thirty": 30, "chaalis": 40, "chalis": 40,
    "chalis": 40, "forty": 40, "pachaas": 50, "pannas": 50, "fifty": 50,
    "saath": 60, "sath": 60, "sixty": 60, "sattar": 70, "seventy": 70,
    "assi": 80, "ainshi": 80, "eighty": 80, "nabbe": 90, "navvad": 90,
    "ninety": 90,
    # Frequent directly-spoken compound amounts in vendor notes.
    "sau": 100, "she": 100, "shambar": 100, "hundred": 100,
    "do_sau": 200, "donshe": 200, "teen_sau": 300, "tinshe": 300,
    "char_sau": 400, "charshe": 400, "paanch_sau": 500, "panchshe": 500,
    "paanchshe": 500, "che_sau": 600, "sahashe": 600, "saat_sau": 700,
    "satshe": 700, "aath_sau": 800, "aathshe": 800, "nau_sau": 900,
    "nau_she": 900, "hazar": 1000, "hazaar": 1000, "hajar": 1000,
    "thousand": 1000, "lakh": 100000, "lac": 100000,
    # Devanagari forms used by Hindi and Marathi STT output.
    "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "बीस": 20, "पचास": 50,
    "सौ": 100, "हजार": 1000, "लाख": 100000, "दोन": 2, "पाच": 5, "सहा": 6,
    "आठ": 8, "दहा": 10, "वीस": 20, "पन्नास": 50, "शंभर": 100,
    "पाचशे": 500, "दोनशे": 200, "तीनशे": 300, "चारशे": 400,
}

MULTIPLIERS = {"sau": 100, "she": 100, "shambar": 100, "hundred": 100,
               "hazar": 1000, "hazaar": 1000, "hajar": 1000, "thousand": 1000,
               "lakh": 100000, "lac": 100000, "सौ": 100, "हजार": 1000,
               "लाख": 100000, "शंभर": 100}
# Only English "and" joins an English compound number. Hindi/Marathi
# conjunctions commonly separate two distinct amounts in a ledger note.
CONNECTORS = {"and"}

TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[\w\u0900-\u097F]+|[^\w\s]", re.UNICODE)


def _canonical(token: str) -> str:
    return token.casefold().replace("-", "_")


def number_from_tokens(tokens: list[str]) -> int | None:
    """Parse a sequence like 'paanch sau' or 'two hundred fifty'."""
    if not tokens:
        return None
    total = current = 0
    seen = False
    for raw in tokens:
        token = _canonical(raw)
        if token in CONNECTORS:
            continue
        if token.isdigit():
            current += int(token); seen = True; continue
        value = UNITS.get(token)
        if value is None:
            return None
        seen = True
        multiplier = MULTIPLIERS.get(token)
        if multiplier:
            current = (current or 1) * multiplier
            if multiplier >= 1000:
                total += current; current = 0
        elif value >= 100 and token not in MULTIPLIERS:
            current += value
        else:
            current += value
    return total + current if seen else None


def normalize_spoken_numbers(text: str) -> str:
    """Convert number words within otherwise untouched multilingual speech to digits."""
    tokens = TOKEN_RE.findall(text)
    output: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _canonical(token) not in UNITS:
            output.append(token); index += 1; continue
        end = index
        sequence: list[str] = []
        while end < len(tokens) and (_canonical(tokens[end]) in UNITS or _canonical(tokens[end]) in CONNECTORS):
            sequence.append(tokens[end]); end += 1
        value = number_from_tokens(sequence)
        # Preserve single simple words unrelated to amounts (e.g. "do" as a verb)
        # unless they are adjacent to an amount marker or form a multi-token number.
        following = _canonical(tokens[end]) if end < len(tokens) else ""
        markers = {"rupaye", "rupee", "rupees", "रुपये", "रुपय", "maal", "cash", "payment", "paid", "का", "चा"}
        if value is not None and (len(sequence) > 1 or following in markers or value >= 20):
            output.append(str(value))
        else:
            output.extend(sequence)
        index = end
    # Compact only spacing around punctuation; leave Devanagari and names unchanged.
    result = " ".join(output)
    return re.sub(r"\s+([,.!?])", r"\1", result)


def normalize_extraction(data: dict) -> dict:
    """Normalize numeric LLM fields without allowing the LLM to calculate balances."""
    cleaned = dict(data)
    for key in ("total_amount", "paid_amount", "outstanding_amount"):
        value = cleaned.get(key)
        if isinstance(value, str):
            normalized = normalize_spoken_numbers(value)
            match = re.search(r"\d+(?:\.\d+)?", normalized)
            cleaned[key] = float(match.group()) if match else None
    return cleaned

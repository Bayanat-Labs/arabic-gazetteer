"""Name keys: script detection, the Arabic cluster key (bayanat-norm-v1), Latin folding and the
looser matching keys used for name families and the baseline matcher."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from arabic_normalize import normalize as _ar_normalize

from .config import AR_GENERIC_TERMS, LATIN_ARTICLES

NORM_POLICY = "bayanat-norm-v1"

_WS = re.compile(r"\s+")
# Letters outside the standard Arabic alphabet that GeoNames uses in Persian, Kurdish or Urdu
# spellings (and, for ڤ and گ, in some Maghrebi and Gulf spellings).
EXTENDED_LETTERS = set("پچژگڤڨکیۀہھےۆێڵڕ")


def _is_arabic_letter(ch: str) -> bool:
    o = ord(ch)
    return (0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF
            or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF)


def _is_latin_letter(ch: str) -> bool:
    if "LATIN" in unicodedata.name(ch, ""):
        return True
    return ch in "ʿʾʻʼ"


def script_of(s: str) -> str:
    """'Arab' or 'Latn' when at least 90% of the letters are in that script, 'mixed' when both
    scripts occur, 'other' otherwise (also for a string with no letters)."""
    ar = la = other = 0
    for ch in s:
        if not (ch.isalpha() or unicodedata.category(ch) in ("Mn", "Lm")):
            continue
        if unicodedata.category(ch) == "Mn":
            continue
        if _is_arabic_letter(ch):
            ar += 1
        elif _is_latin_letter(ch):
            la += 1
        else:
            other += 1
    total = ar + la + other
    if total == 0:
        return "other"
    if ar / total >= 0.9:
        return "Arab"
    if la / total >= 0.9:
        return "Latn"
    if ar and la:
        return "mixed"
    return "other"


def clean(s: str) -> str:
    """NFC, outer whitespace removed, inner whitespace runs collapsed to one space."""
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


# Invisible format controls that some source names carry: zero-width space, non-joiner and
# joiner, left-to-right and right-to-left marks (U+200B-U+200F), bidi embeddings and overrides
# (U+202A-U+202E), bidi isolates (U+2066-U+2069), the Arabic letter mark (U+061C) and the byte
# order mark / zero-width no-break space (U+FEFF).
FORMAT_CONTROLS = frozenset(
    [chr(c) for c in range(0x200B, 0x2010)] + [chr(c) for c in range(0x202A, 0x202F)]
    + [chr(c) for c in range(0x2066, 0x206A)] + ["\u061c", "\ufeff"])
_FORMAT_CONTROLS_RE = re.compile("[" + "".join(sorted(FORMAT_CONTROLS)) + "]")
FORMAT_CONTROL_ISSUE = "format_control"


def has_format_controls(s: str | None) -> bool:
    return bool(s) and _FORMAT_CONTROLS_RE.search(s) is not None


def strip_format_controls(s: str) -> str:
    """The string without the invisible format controls listed in FORMAT_CONTROLS."""
    return _FORMAT_CONTROLS_RE.sub("", s)


def visible(s: str) -> str:
    """The displayed form of a name: format controls removed, then clean()."""
    return clean(strip_format_controls(s))


def name_issues(issue: str | None) -> list[str]:
    """The issues of a name row: name_issue holds one value or several joined by commas."""
    return issue.split(",") if issue else []


def script_issue(issue: str | None) -> str | None:
    """name_issue without format_control: the script issue of the name, if any."""
    rest = [x for x in name_issues(issue) if x != FORMAT_CONTROL_ISSUE]
    return ",".join(rest) or None


@lru_cache(maxsize=1_000_000)
def ar_norm(s: str) -> str:
    """Arabic cluster key: bayanat-norm-v1 (arabic-normalize), then whitespace collapsed."""
    return _WS.sub(" ", _ar_normalize(strip_format_controls(s), NORM_POLICY)).strip()


_AR_FOLD = str.maketrans({"ة": "ه", "ؤ": "و", "ئ": "ي", "ء": None, "ک": "ك", "ی": "ي",
                          "ۀ": "ه", "ہ": "ه", "ھ": "ه", "ے": "ي", "ڨ": "ق", "گ": "ك",
                          "ڤ": "ف", "پ": "ب", "چ": "ج", "ژ": "ز", "ٱ": "ا"})
_AR_PUNCT = re.compile(r"[،؛؟٫٬۔.,;:!?()\[\]{}\"'«»\-_/\\|·•–—]+")


@lru_cache(maxsize=1_000_000)
def ar_match_key(s: str) -> str:
    """Looser Arabic key for name families and matching: the cluster key with ة→ه, hamza seats
    folded (ؤ→و, ئ→ي, ء removed), Persian letter forms mapped to Arabic ones, punctuation removed
    and the article ال removed from the start of each word (when two or more letters remain)."""
    t = _AR_PUNCT.sub(" ", ar_norm(s)).translate(_AR_FOLD)
    words = []
    for w in t.split():
        if w.startswith("ال") and len(w) >= 4:
            w = w[2:]
        words.append(w)
    return " ".join(words)


def ar_core_key(key: str) -> str:
    """The matching key without one leading generic word (حي، مدينة، محافظة ...)."""
    words = key.split()
    if len(words) >= 2 and words[0] in _GENERIC:
        return " ".join(words[1:])
    return key


_GENERIC = {ar_match_key(w) for w in AR_GENERIC_TERMS} | set(AR_GENERIC_TERMS)

_LATIN_MARKS = str.maketrans({c: None for c in "ʿʾʻʼ'`‘’´"})
_LATIN_PUNCT = re.compile(r"[^0-9a-z ]+")
_LATIN_SPECIAL = str.maketrans({"ı": "i", "ł": "l", "ø": "o", "đ": "d", "ð": "d", "þ": "th",
                                "æ": "ae", "œ": "oe", "ß": "ss", "ħ": "h"})


@lru_cache(maxsize=1_000_000)
def latin_fold(s: str) -> str:
    """Latin cluster key: compatibility decomposition, combining marks removed, case folded,
    ʿ ʾ and apostrophes removed, other punctuation and hyphens read as spaces."""
    t = unicodedata.normalize("NFKD", strip_format_controls(s))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.casefold().translate(_LATIN_SPECIAL).translate(_LATIN_MARKS)
    t = _LATIN_PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


_ARTICLES = set(LATIN_ARTICLES)
_DOUBLE = re.compile(r"([a-z])\1+")


@lru_cache(maxsize=1_000_000)
def latin_match_key(s: str) -> str:
    """Looser Latin key: the cluster key with leading articles (al, el, ash ...) removed from
    each word, doubled letters collapsed, final -ah/-eh read as -a, ou→u, ee→i, oo→u."""
    words = []
    raw = latin_fold(s).split()
    for i, w in enumerate(raw):
        if w in _ARTICLES and i + 1 < len(raw):
            continue
        w = w.replace("ou", "u").replace("ee", "i").replace("oo", "u")
        w = _DOUBLE.sub(r"\1", w)
        if len(w) > 3 and (w.endswith("ah") or w.endswith("eh")):
            w = w[:-2] + "a"
        words.append(w)
    return " ".join(words)


def name_issue(name: str, script: str, slot: str) -> str | None:
    """Flag for names whose script does not fit their language tag (slot is 'ar' or 'latin'),
    with ',format_control' added (or 'format_control' alone) when the name contains invisible
    format controls. The script is that of the name without format controls."""
    base = _script_issue(name, script, slot)
    if has_format_controls(name):
        return f"{base},{FORMAT_CONTROL_ISSUE}" if base else FORMAT_CONTROL_ISSUE
    return base


def _script_issue(name: str, script: str, slot: str) -> str | None:
    if slot == "ar":
        if script != "Arab":
            return "not_arabic_script"
        if any(ch in EXTENDED_LETTERS for ch in name):
            return "extended_letters"
        return None
    if script == "Arab":
        return "arabic_script_in_latin_slot"
    if script not in ("Latn",):
        return "not_latin_script"
    return None

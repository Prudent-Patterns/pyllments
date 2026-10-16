"""
Token estimates without a tokenizer: a port of tokenx's segment rules.

The text is split into words, punctuation runs and whitespace, and each segment
is priced by the first rule that fits it. Every ratio is calibrated against
OpenAI's o200k_base encoding; other vocabularies land near it, not on it.
Known gaps, from tokenx: base64 and hashes come out about 70% low, Thai, Hebrew,
Arabic and Hindi 30-60% low.

Ported from tokenx (https://github.com/johannschopplich/tokenx, src/segments.ts
at d262eb5), MIT License, Copyright (c) 2023-PRESENT Johann Schopplich.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Sequence


@dataclass(frozen=True)
class LanguageConfig:
    """Characters per token for segments that match ``pattern``."""

    pattern: re.Pattern
    average_chars_per_token: float


_WHITESPACE = re.compile(r"\s+")
_STRUCTURED_WHITESPACE = re.compile(r"\n\s")
# JavaScript sees a character outside the basic plane as two code units in
# \u0080-￿; Python sees one code point, so the range reaches the top.
_NON_ASCII = re.compile("[\u0080-\U0010ffff]")
_CJK = re.compile(
    "[一-鿿㐀-䶿　-ヿ＀-￯⺀-⻿㇀-㇯"
    "㈀-㋿㌀-㏿가-힯ᄀ-ᇿ㄰-㆏ꥠ-꥿"
    "ힰ-퟿]"
)
_NUMERIC = re.compile(r"\d+", re.ASCII)
_PUNCTUATION_CLASS = r"""[.,!?;(){}\[\]<>:/\\|@#$%^&*+=`~_"-]"""
_PUNCTUATION = re.compile(_PUNCTUATION_CLASS)
# Chinese and Japanese put no spaces between words; without this a whole
# paragraph would be one segment.
_CJK_PUNCTUATION_CLASS = (
    "[、-〃〈-】〔-〟〰・！-／：-＠"
    "［-｀｛-･]"
)
_CJK_PUNCTUATION = re.compile(_CJK_PUNCTUATION_CLASS)
_LOWERCASE_WORD = re.compile(r"[a-z]+")
_SPLIT = re.compile(rf"(\s+|{_PUNCTUATION_CLASS}+|{_CJK_PUNCTUATION_CLASS}+)")

# Python's re has no \p{Extended_Pictographic}; these ranges cover the emoji
# blocks and the older symbols that render as emoji.
_PICTOGRAPHIC = (
    "©®‼⁉™ℹ↔-↙↩↪⌚⌛"
    "⌨⏏⏩-⏳⏸-⏺Ⓜ▪▫▶◀"
    "◻-◾☀-➿⤴⤵⬅-⬇⬛⬜⭐⭕"
    "〰〽㊗㊙\U0001f000-\U0001faff"
)
_EMOJI_COMPONENT = "#*0-9‍⃣️\U0001f1e6-\U0001f1ff\U0001f3fb-\U0001f3ff\U000e0020-\U000e007f"

DEFAULT_CHARS_PER_TOKEN = 7.0
_SHORT_TOKEN_THRESHOLD = 3
_LOWERCASE_WORD_SINGLE_TOKEN_LENGTH = 8
_PUNCTUATION_CHARS_PER_TOKEN = 6
_KANA_CHARS_PER_TOKEN = 1.35
_HANGUL_CHARS_PER_TOKEN = 1.65
_HANZI_CHARS_PER_TOKEN = 1.2

DEFAULT_LANGUAGE_CONFIGS: tuple[LanguageConfig, ...] = (
    # An accent rule prices a whole language through the minority of its words
    # that carry an accent, so each ratio is fitted against running text.
    LanguageConfig(re.compile("[äöüßẞ]", re.IGNORECASE), 3),
    LanguageConfig(re.compile("[éèêëàâîïôûùüÿçœæáíóúñ]", re.IGNORECASE), 4.5),
    # Below what accented segments alone would fit: unaccented Slavic words
    # fall through to the default ratio, and this makes up the shortfall.
    LanguageConfig(re.compile("[ąćęłńóśźżěščřžýůúďťň]", re.IGNORECASE), 2.5),
    LanguageConfig(re.compile("[а-яё]", re.IGNORECASE), 6),
    LanguageConfig(re.compile("[ά-ώ]", re.IGNORECASE), 3),
    # Anchored to pure emoji runs: ™ is pictographic too, and an unanchored
    # match would misprice the whole word it is attached to.
    LanguageConfig(re.compile(f"^[{_PICTOGRAPHIC}][{_PICTOGRAPHIC}{_EMOJI_COMPONENT}]*\\Z"), 0.9),
)


def estimate_tokens(
    text: Optional[str],
    *,
    default_chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    language_configs: Sequence[LanguageConfig] = (),
) -> int:
    """
    Estimated o200k token count of ``text``.

    ``language_configs`` are checked before the built-in ones, and the first
    match wins; ``default_chars_per_token`` prices segments no rule claims.
    """
    if not text:
        return 0
    return sum(count for _, count in walk_segments(text, default_chars_per_token, language_configs))


def walk_segments(
    text: str,
    default_chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    language_configs: Sequence[LanguageConfig] = (),
) -> Iterator[tuple[str, int]]:
    """(segment, estimated tokens) pairs; the segments join back into ``text``."""
    previous = ""
    parts = _SPLIT.split(text)
    i = 0
    while i < len(parts):
        segment = parts[i]
        # A CJK punctuation run joins the clause before it, but only a clause
        # with CJK in it: a Latin word keeps its own pricing.
        following = parts[i + 1] if i + 1 < len(parts) else ""
        if _CJK_PUNCTUATION.search(following) and _CJK.search(segment):
            segment += following
            i += 1
        if segment:
            yield segment, _segment_tokens(segment, previous, default_chars_per_token, language_configs)
            previous = segment
        i += 1


def _segment_tokens(
    segment: str,
    previous: str,
    default_chars_per_token: float,
    language_configs: Sequence[LanguageConfig],
) -> int:
    if _WHITESPACE.fullmatch(segment):
        # Indentation and blank lines cost a token in o200k.
        if _STRUCTURED_WHITESPACE.search(segment):
            return 1
        # Whitespace without a line break merges. A line break merges into the
        # punctuation before it but stands alone after a word.
        if "\n" not in segment:
            return 0
        last = previous[-1:]
        return 0 if _PUNCTUATION.search(last) or _CJK_PUNCTUATION.search(last) else 1

    # Caller configs take precedence over every rule but whitespace.
    custom = _chars_per_token(segment, language_configs)
    if custom is not None:
        return math.ceil(len(segment) / custom)

    if _CJK.search(segment):
        return _cjk_tokens(segment)

    # Every built-in config needs a non-ASCII character to match.
    built_in = _chars_per_token(segment, DEFAULT_LANGUAGE_CONFIGS) if _NON_ASCII.search(segment) else None
    if built_in is not None:
        return math.ceil(len(segment) / built_in)

    # o200k groups digit runs into chunks of up to three.
    if _NUMERIC.fullmatch(segment):
        return math.ceil(len(segment) / 3)

    length = _js_length(segment)
    if length <= _SHORT_TOKEN_THRESHOLD:
        return 1
    # o200k merges common lowercase words of up to eight letters into one token.
    if length <= _LOWERCASE_WORD_SINGLE_TOKEN_LENGTH and _LOWERCASE_WORD.fullmatch(segment):
        return 1
    if _PUNCTUATION.search(segment):
        return math.ceil(length / _PUNCTUATION_CHARS_PER_TOKEN)
    return math.ceil(length / default_chars_per_token)


def _chars_per_token(segment: str, configs: Iterable[LanguageConfig]) -> Optional[float]:
    for config in configs:
        if config.pattern.search(segment):
            return config.average_chars_per_token
    return None


def _js_length(segment: str) -> int:
    """tokenx's ``segment.length``: UTF-16 code units, two for an astral character."""
    return len(segment) + sum(1 for ch in segment if ord(ch) > 0xFFFF)


def _cjk_tokens(segment: str) -> int:
    kana = hangul = hanzi = 0
    for ch in segment:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            kana += 1
        elif _is_hangul(code):
            hangul += 1
        else:
            hanzi += 1
    # One rounding for the whole segment, so script boundaries cost nothing.
    return math.ceil(
        hanzi / _HANZI_CHARS_PER_TOKEN + kana / _KANA_CHARS_PER_TOKEN + hangul / _HANGUL_CHARS_PER_TOKEN
    )


def _is_hangul(code: int) -> bool:
    return (
        0xAC00 <= code <= 0xD7AF
        or 0x1100 <= code <= 0x11FF
        or 0x3130 <= code <= 0x318F
        or 0xA960 <= code <= 0xA97F
        or 0xD7B0 <= code <= 0xD7FF
    )

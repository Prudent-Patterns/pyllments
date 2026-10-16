"""
The token estimate: tokenx's segment rules, ported.

The golden counts come from tokenx itself (src/index.ts at d262eb5, run under
Node), so a drift in the port shows up here rather than in a window's size.
"""

import re

import pytest

from pyllments.common.token_estimate import LanguageConfig, estimate_tokens, walk_segments
from pyllments.common.tokenizers import get_token_len

TOKENX_GOLDEN = [
    ("My glucose was 5.6 mmol/L after lunch, and 7.2 mmol/L two hours later.", 23),
    ("Medications: lisinopril 10 mg once daily; hydrochlorothiazide 12.5 mg.", 18),
    ("def f(x):\n    if x > 0:\n        return x * 2\n\n    return -x\n", 21),
    ("我今天的血糖是5.6 mmol/L，还好吗？", 17),
    ("コーヒー文化が広まるにつれ、抽出法が工夫され始めた。", 21),
    ("Ursprünglich konnten sich nur gut situierte Bürger das Getränk leisten.", 18),
    ("В России кофе появился при царе Алексее Михайловиче.", 12),
    ("Feeling great today 😀👍🏽 thanks! 🎉🎉 ™ ©", 16),
    ("1234567 89 2026", 6),
]


@pytest.mark.parametrize("text,expected", TOKENX_GOLDEN)
def test_the_port_counts_what_tokenx_counts(text, expected):
    assert estimate_tokens(text) == expected


def test_segments_join_back_into_the_text():
    text = "Line one.\n\n  indented — ünïcode 你好，世界。 😀 end"
    assert "".join(segment for segment, _ in walk_segments(text)) == text


def test_nothing_costs_nothing():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


def test_spaces_merge_and_a_line_break_costs_only_after_a_word():
    assert estimate_tokens("one two") == 2
    assert estimate_tokens("word\nword") == 3
    assert estimate_tokens("word.\nword") == 3  # the break merges into the full stop
    assert estimate_tokens("a\n    b") == 3  # indentation costs a token


def test_digits_go_in_threes():
    assert estimate_tokens("1234567") == 3


def test_a_short_lowercase_word_is_one_token_and_a_long_one_is_priced_by_length():
    assert estimate_tokens("medicine") == 1
    assert estimate_tokens("hydrochlorothiazide") == 3


def test_a_caller_config_wins_over_the_built_in_rules():
    configs = [LanguageConfig(re.compile("[a-z]"), 2)]
    assert estimate_tokens("medicine", language_configs=configs) == 4


def test_get_token_len_is_the_estimate_for_any_model_name():
    text = TOKENX_GOLDEN[0][0]
    assert get_token_len(text, "gpt-4o") == get_token_len(text, "claude-haiku") == estimate_tokens(text)

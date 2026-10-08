from pyllments.payloads.message.usage import normalize_usage


def test_a_record_passes_through_with_every_key():
    assert normalize_usage({"input_tokens": 9, "cached_input_tokens": 4, "output_tokens": 2}) == {
        "input_tokens": 9, "cached_input_tokens": 4, "cache_write_tokens": 0, "output_tokens": 2,
    }


def test_chat_completions_usage_is_read():
    raw = {"prompt_tokens": 50, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 32}}
    assert normalize_usage(raw) == {
        "input_tokens": 50, "cached_input_tokens": 32, "cache_write_tokens": 0, "output_tokens": 5,
    }


def test_no_counts_is_none():
    assert normalize_usage(None) is None
    assert normalize_usage({}) is None
    assert normalize_usage({"something": 1}) is None

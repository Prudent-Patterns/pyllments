from pyllments.common.token_estimate import estimate_tokens


def get_token_len(text: str, model: str = "gpt-4o-mini") -> int:
    """
    Estimated token length of a string.

    ``model`` names the vocabulary to estimate for. Every model shares the
    o200k-calibrated rates for now; per-vocabulary rates would be chosen here.
    """
    return estimate_tokens(text)

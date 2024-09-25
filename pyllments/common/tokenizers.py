from functools import cache

import tiktoken
# TODO: Add more tokenizers/models still using string lookup
@cache
def get_token_len(text: str, model: str = "gpt-4o-mini") -> int:
    """Calculates the token length of a string given a particular OpenAI model"""
    if model is None: # Useful when augmenting classes
        model = "gpt-4o-mini"
    tokenizer = tiktoken.encoding_for_model(model)
    return len(tokenizer.encode(text))
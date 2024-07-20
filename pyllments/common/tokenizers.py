import tiktoken

def get_token_len(text: str, model: str = "gpt-4o-mini") -> int:
    tokenizer = tiktoken.encoding_for_model(model)
    return len(tokenizer.encode(text))
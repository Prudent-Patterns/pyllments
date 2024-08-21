from numpy import ndarray
from sentence_transformers import SentenceTransformer


def base_sentence_transformer_encode(
        sentences: list[str], 
        model_name: str = 'Alibaba-NLP/gte-base-en-v1.5') -> ndarray:
    model = SentenceTransformer(model_name)
    return model.encode(sentences)
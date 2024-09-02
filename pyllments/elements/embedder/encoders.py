from numpy import ndarray
import param
from sentence_transformers import SentenceTransformer


class SentenceTransformerEncoder(param.parameterized):
    model_name = param.String(default="'Alibaba-NLP/gte-base-en-v1.5'", doc="""
        The name of the model to use""")
    
    model = param.ClassSelector(class_=SentenceTransformer)
    embedding_dims = param.Integer(default=768, doc="""
        The dimension of the embedding""")
    cache_folder = param.String(default=None)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = SentenceTransformer(
            self.model_name,
            trust_remote_code=True,
            cache_folder=self.cache_folder
        )
        self.embedding_dims = self.model.get_sentence_embedding_dimension()

    def encode(self, sentences: list[str]) -> ndarray:
        return self.model.encode(sentences)
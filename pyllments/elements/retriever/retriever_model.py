import param
import pyarrow as pa

from pyllments.base.model_base import Model
from pyllments.common.collections import LanceDBCollection, Collection
# from pyllments.common.tokenizers import get_token_len
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload


default_lance_db_schema = pa.schema([
    pa.field('text', pa.string()),
    pa.field('embedding', pa.list_(pa.float32(), 768)),
    pa.field('source_file', pa.string()),
    pa.field('start_idx', pa.int32()),
    pa.field('end_idx', pa.int32())
])

def pa_schema_to_col_list(schema: pa.Schema):
    return schema.empty_table().column_names

class RetrieverModel(Model):
    collection = param.ClassSelector(class_=Collection, doc="""
        The collection to retrieve from. Based on a a DB backend for storage""")
    collection_name = param.String(default="", doc="""
        The name of the collection""")
    url = param.String(default="", doc="""
        The url of the database""")
    embedding_dims = param.Integer(default=768, doc="""
        The dimension of the embedding""")
    schema = param.Parameter(default=default_lance_db_schema, doc="""
    The schema used with the collection. If the Collection is based on
    LanceDB, pyarrow schemas are preferred.
    """)
    schema_cols = param.List()
    metric = param.String(default="cosine", doc="""
        The metric used to search the collection""")
    retrieval_n = param.Integer(default=5, doc="""
        The number of results to return""")
    # TODO: Implement token limits for retrieval if necessary
    retrieval_token_limit = param.Integer(default=None, doc="""
        The token limit of the model""")
    retrieval_tokenizer_model = param.String(default="gpt-4o-mini", doc="""
        The model used to tokenize the text""")

    def __init__(self, retrieval_token_limit=None, **params):
        super().__init__(**params)
        if not self.collection_name:
            # Uses default param-generated RetrievelModel name if not set
            self.collection_name = self.name

        self.schema_cols = pa_schema_to_col_list(self.schema)
        self.collection = LanceDBCollection(
            collection_name=self.collection_name,
            schema=self.schema
        )
    
    def add_item(self, chunk_payload: ChunkPayload):
        item = {col: getattr(chunk_payload.model, col) for col in self.schema_cols}
        self.collection.add_item(item)
    
    def retrieve(self, message_payload: MessagePayload):
        embedding = message_payload.model.embedding
        chunk_payloads = [
            ChunkPayload(**item)
            for item in self.collection.query(
                embedding,
                n=self.retrieval_n,
                metric=self.metric)
        ]
        return chunk_payloads
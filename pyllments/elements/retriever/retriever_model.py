import param
import pyarrow as pa
import time
from loguru import logger

from pyllments.base.model_base import Model
from pyllments.common.collections import LanceDBCollection, Collection
# from pyllments.common.tokenizers import get_token_len
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload


default_lance_db_schema = pa.schema([
    pa.field('text', pa.string()),
    pa.field('embedding', pa.list_(pa.float32(), 768)),
    pa.field('source_filepath', pa.string()),
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
    url = param.String(default="data/lancedb", doc="""
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
    # Temporary storage of retrieved and added chunks
    retrieved_chunks = param.List(item_type=ChunkPayload, doc="""
        The chunks retrieved from the collection""")
    created_chunks = param.List(item_type=ChunkPayload, doc="""
        The chunks created by the model""")

    def __init__(self, retrieval_token_limit=None, **params):
        super().__init__(**params)
        if not self.collection_name:
            # Uses default param-generated RetrievelModel name if not set
            self.collection_name = self.name

        self.schema_cols = pa_schema_to_col_list(self.schema)
        self.collection = LanceDBCollection(
            url=self.url,
            collection_name=self.collection_name,
            schema=self.schema
        )
    
    def add_item(self, chunk_payload: ChunkPayload):
        start_time = time.time()
        
        item = {col: getattr(chunk_payload.model, col) for col in self.schema_cols}
        self.collection.add_item(item)

        logger.info(f"RetrieverModel: Added item to collection. Time elapsed: {time.time() - start_time:.2f} seconds")

    def add_items(self, chunk_payloads: list[ChunkPayload]):
        start_time = time.time()

        self.created_chunks = chunk_payloads
        
        items = [{col: getattr(chunk_payload.model, col) for col in self.schema_cols} for chunk_payload in chunk_payloads]
        self.collection.add_items(items)
        
        logger.info(f"RetrieverModel: Added {len(chunk_payloads)} items to collection. Time elapsed: {time.time() - start_time:.2f} seconds")
    
    def retrieve(self, message_payload: MessagePayload):
        start_time = time.time()
        embedding = message_payload.model.embedding
        if embedding is None:
            raise ValueError("No embedding found in MessagePayload")
        logger.info("RetrieverModel: Starting query")
        chunk_payloads = [
            ChunkPayload(**item)
            for item in self.collection.query(
                embedding,
                n=self.retrieval_n,
                metric=self.metric)
        ]
        self.retrieved_chunks = chunk_payloads
        logger.info(f"RetrieverModel: Query completed. Time elapsed: {time.time() - start_time:.2f} seconds")
    
        return chunk_payloads
    
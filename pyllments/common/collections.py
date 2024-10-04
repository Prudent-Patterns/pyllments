import lancedb
import numpy as np
import param
import pyarrow as pa
import time
# TODO: May need their own folders

class Collection(param.Parameterized):
    url = param.String(default="", doc="""
        The url of the data folder""")
    collection_name = param.String(default="default", doc="""
        The name of the collection""")
    db = param.Parameter(default=None)
    collection = param.Parameter(default=None)

    def load_db(self, url: str):
        """Loads a database from a url or creates a new one"""
        pass

    def load_collection(self, collection_name: str):
        """Loads a collection from the database"""
        pass

    def add_items(self, items: list[dict]):
        pass

default_lance_db_schema = pa.schema([
    pa.field('text', pa.string()),
    pa.field('embedding', pa.list_(pa.float32(), 768)),
    pa.field('source_filepath', pa.string()),
    pa.field('start_idx', pa.int32()),
    pa.field('end_idx', pa.int32())
])


class LanceDBCollection(Collection):
    url = param.String(default="data/lancedb", doc="""
        The url of the database""")
    schema = param.Parameter(
        default=default_lance_db_schema,
        doc="""The pydantic schema of the collection""")
    metric = param.String(default="cosine", doc="""
        The metric used to search the collection""")
    n = param.Integer(default=5, doc="""
        The number of results to return""")
    
    def __init__(self, **params):
        super().__init__(**params)
        self.load_collection(self.collection_name)
    
    def load_collection(self, collection_name: str):
        """Loads a collection from the database"""
        self.db = lancedb.connect(self.url)
        self.collection = self.db.create_table(
            name=self.collection_name,
            schema=self.schema,
            exist_ok=True)
        
    def add_item(self, item: dict):
        """Adds an item to the collection"""
        # item['embedding'] = list(item['embedding'].astype(np.float32))
        self.collection.add([item])

    def add_items(self, items: list[dict]):
        """Adds items to the collection"""
        self.collection.add(items)

    def query(self, embedding: np.ndarray, n: int = None, metric: str = None):
        """Queries the collection. If n or metric are not provided, uses the class defaults"""
        if n is None:
            n = self.n
        if metric is None:
            metric = self.metric
        start_time = time.time()
        results = self.collection.search(embedding) \
            .metric(metric) \
            .limit(n) \
            .to_list()
        for result in results:
            result['distance'] = result['_distance']
            del result['_distance']
        return results
    
    def get_random_items(self, n: int, column_name: str = 'text', get_dict: bool = False):
        """
        Gets random items from the collection. If column_name provided, returns an
        n-length list of values. If get_dict is True, returns a dictionary.
        """
        lance_table = self.collection.to_lance()
        if get_dict:
            return lance_table.sample(n).to_pydict()
        else:
            return lance_table.sample(n).column(column_name).to_pylist()
    
    def delete_collection(self):
        """Deletes the collection"""
        self.collection.drop_table(self.collection_name)

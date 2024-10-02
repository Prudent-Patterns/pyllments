import param

from pyllments.base.model_base import Model
from pyllments.elements.chunker.splitters import base_text_splitter
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.file import FilePayload

class TextChunkerModel(Model):
    
    chunk_size = param.Integer(default=1000, doc="The size of the chunks to be created")
    chunk_overlap = param.Integer(default=200, doc="The overlap of the chunks to be created")

    splitter_fn = param.Callable(default=base_text_splitter, doc="Should return a list of Chunk Payloads given a File Payload")
    file_types = param.List(default=['txt', 'md'])
    multi_proc = param.Boolean(default=False, doc="When True, multiple processes will handle the files simultaneously")
    
    def __init__(self, **params):
        super().__init__(**params)

    def make_chunks(self, file_payload: FilePayload) -> list[ChunkPayload]:
        """
        Create chunks from a single file payload.
        
        Parameters:
        -----------
        file_payload : FilePayload
            The file payload to be chunked.
        
        Returns:
        --------
        list[ChunkPayload]
            A list of chunk payloads created from the input file.
        """
        chunks = []
        for chunk in self.splitter_fn(
            file_payload.model.b_file, 
            chunk_size=self.chunk_size, 
            chunk_overlap=self.chunk_overlap):
            chunks.append(
                ChunkPayload(
                    text=chunk.text,
                    source_filepath=file_payload.model.local_path,
                    start_idx=chunk.start_index,
                    end_idx=chunk.end_index
                )
            )
        return chunks
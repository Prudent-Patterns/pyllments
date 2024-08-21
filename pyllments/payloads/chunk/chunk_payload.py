from typing import Optional
from pathlib import Path
from pyllments.base.payload_base import Payload
from pyllments.payloads.chunk.chunk_model import ChunkModel

class ChunkPayload(Payload):
    def __init__(
        self,
        text: str = '',
        source_file: Optional[Path] = None,
        strategy: Optional[str] = None,
        start_idx: int = None,
        end_idx: int = None,
        embedding = None, 
        **params
    ):
        super().__init__(**params)
        self.model = ChunkModel(
            text=text,
            source_file=source_file,
            strategy=strategy,
            start_idx = start_idx,
            end_idx = end_idx,
            embedding = embedding
        )
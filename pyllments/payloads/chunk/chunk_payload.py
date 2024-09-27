from typing import Optional
from pathlib import Path
from pyllments.base.payload_base import Payload
from pyllments.payloads.chunk.chunk_model import ChunkModel

class ChunkPayload(Payload):
    def __init__(self, **params):
        super().__init__(**params)
        self.model = ChunkModel(**params)
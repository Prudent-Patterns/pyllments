from collections import deque
from pathlib import Path

from typing import List

import param
from loguru import logger
from sqlite_utils import Database

from pyllments.base.model_base import Model
from pyllments.common.tokenizers import get_token_len
from pyllments.payloads.message import MessagePayload
from pyllments.serve import LoopRegistry


class HistoryHandlerModel(Model):
    """
    Model for handling chat history with optional SQLite persistence.
    When persist=True, messages are stored in SQLite and loaded on startup.
    When persist=False, messages are only kept in memory and lost on restart.
    """
    history_token_limit = param.Integer(default=32000, bounds=(1, None), doc="""
        The max amount of tokens to keep in the history""")
    history = param.ClassSelector(class_=deque, default=deque())
    history_token_count = param.Integer(default=0, bounds=(0, None), doc="""
        The amount of tokens in the history""")

    context_token_limit = param.Integer(default=16000, bounds=(0, None), doc="""
        The amount of tokens to keep in the context window""")
    context = param.ClassSelector(class_=deque, default=deque(), instantiate=True)
    context_token_count = param.Integer(default=0, bounds=(0, None), doc="""
        The amount of tokens in the context window""")

    tokenizer_model = param.String(default="gpt-4o")
    
    persist = param.Boolean(default=False, doc="""
        Whether to persist messages to SQLite. If False, messages are only kept in memory.""")
    
    # Database parameters only used when persist=True
    db_path = param.String(default=None, doc="The path to the history database")

    def __init__(self, **params):
        super().__init__(**params)
        
        if self.persist:
            # Initialize database-related attributes only if persistence is enabled
            self._pending_deletes: List[float] = []
            self._pending_inserts: List[MessagePayload] = []
            self._db_setup()

    def _db_setup(self):
        """Sets up the SQLite database and loads existing messages."""
        # Set up database path
        path = Path(self.db_path) if self.db_path else Path(f"{self.name}.db")
        if not path.suffix == '.db':
            path = path / f"{self.name}.db"
        self.db_path = str(path)
        
        # Initialize database and table
        self.db = Database(self.db_path)
        self.table = self.db['history']
        
        # Create table if it doesn't exist
        if not self.table.exists():
            self.table.create({
                "role": str,
                "content": str,
                "mode": str,
                "timestamp": float
            }, pk="timestamp")
            return  # No messages to load from a new table
        
        # Load existing messages ordered by timestamp
        rows = self.table.rows_where(order_by="timestamp")
        messages = []
        for row in rows:
            try:
                message = MessagePayload(
                    role=row['role'],
                    content=row['content'],
                    mode=row.get('mode', 'atomic'),
                    timestamp=row['timestamp']
                )
                messages.append(message)
            except Exception as e:
                logger.warning(f"Failed to load message from database: {e}")
                continue
        
        # Load messages into history (which will also handle context population)
        if messages:
            self.load_messages(messages)

    def update_history(self, message: MessagePayload, token_estimate: int):
        if token_estimate > self.history_token_limit:
            raise ValueError(
                f"The token count ({token_estimate}) of the new message exceeds the history limit ({self.history_token_limit})."
            )
            
        # Track messages to be deleted if persistence is enabled
        deleted_messages = []
        
        # Remove messages from history until the new message will fit
        while (
            self.history_token_count + token_estimate >
            self.history_token_limit
        ):
            popped_message, popped_token_count = self.history.popleft()
            self.history_token_count -= popped_token_count
            if self.persist:
                deleted_messages.append(popped_message)

        self.history.append((message, token_estimate))
        self.history_token_count += token_estimate
        
        # Update database if persistence is enabled
        if self.persist and (deleted_messages or message):
            # Add to pending changes
            self._pending_deletes.extend(msg.model.timestamp for msg in deleted_messages)
            self._pending_inserts.append(message)
            
            # Trigger database update
            loop = LoopRegistry.get_loop()
            loop.create_task(self._sync_database())

    async def _sync_database(self):
        """Synchronizes pending changes with the database in a single transaction."""
        if not self._pending_deletes and not self._pending_inserts:
            return

        # Get pending changes
        deletes = self._pending_deletes.copy()
        inserts = [{
            "role": msg.model.role,
            "content": msg.model.content,
            "mode": msg.model.mode,
            "timestamp": msg.model.timestamp
        } for msg in self._pending_inserts]
        
        # Clear pending changes
        self._pending_deletes.clear()
        self._pending_inserts.clear()

        # Execute in thread pool
        try:
            await LoopRegistry.get_loop().run_in_executor(
                None,
                self._execute_db_operations,
                inserts,
                deletes
            )
        except Exception as e:
            logger.error(f"Error syncing database: {e}")

    def _execute_db_operations(self, inserts: List[dict], deletes: List[float]):
        """Executes database operations in a single transaction."""
        with self.db.conn:  # This automatically handles the transaction
            if deletes:
                self.table.delete_where(
                    "timestamp IN (" + ",".join("?" * len(deletes)) + ")",
                    deletes
                )
            if inserts:
                self.table.insert_all(inserts)

    def load_messages(self, messages: list[MessagePayload]):
        """Batch load multiple messages efficiently."""
        # Calculate token estimates for all messages first
        message_tokens = [
            (msg, get_token_len(msg.model.content, self.tokenizer_model))
            for msg in messages
        ]
        
        # Update history and context in batch
        for message, token_estimate in message_tokens:
            self.update_history(message, token_estimate)
            self.update_context(message, token_estimate)
        
        # Trigger context update only once after all messages are processed
        self.param.trigger('context')

    def load_message(self, message: MessagePayload):
        """Load a single message. For backwards compatibility."""
        self.load_messages([message])

    def update_context(self, message: MessagePayload, token_estimate: int):
        if token_estimate > self.context_token_limit:
            raise ValueError(
                f"The token count ({token_estimate}) of the new message exceeds the context limit ({self.context_token_limit})."
            )
        while (
            self.context_token_count + token_estimate >
            self.context_token_limit
        ):
            popped_message, popped_token_count = self.context.popleft()
            self.context_token_count -= popped_token_count

        self.context.append((message, token_estimate))
        self.context_token_count += token_estimate

    def get_context_messages(self) -> list[MessagePayload]:
        return [message for message, _ in self.context]

    def get_history_messages(self) -> list[MessagePayload]:
        return [message for message, _ in self.history]
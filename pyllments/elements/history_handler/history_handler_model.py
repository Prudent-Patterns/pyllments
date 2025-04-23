from collections import deque
from pathlib import Path
from typing import List, Union, Tuple

import param
from loguru import logger
from sqlite_utils import Database

from pyllments.base.model_base import Model
from pyllments.common.tokenizers import get_token_len
from pyllments.payloads import MessagePayload, ToolsResponsePayload
from pyllments.common.loop_registry import LoopRegistry


class HistoryHandlerModel(Model):
    """
    Model for handling chat history with optional SQLite persistence.
    When persist=True, messages and tool responses are stored in SQLite and loaded on startup.
    When persist=False, messages and tool responses are only kept in memory and lost on restart.
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
            self._pending_inserts: List[Union[MessagePayload, ToolsResponsePayload]] = []
            self._db_setup()

    def _db_setup(self):
        """Sets up the SQLite database and loads existing messages and tool responses."""
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
                "type": str,  # 'message' or 'tool_response'
                "role": str,  # For messages
                "content": str,
                "mode": str,  # For messages
                "tool_responses": str,  # JSON string for tool responses
                "timestamp": float
            }, pk="timestamp")
            return  # No entries to load from a new table
        
        # Load existing entries ordered by timestamp
        rows = self.table.rows_where(order_by="timestamp")
        entries = []
        for row in rows:
            try:
                if row['type'] == 'message':
                    entry = MessagePayload(
                        role=row['role'],
                        content=row['content'],
                        mode=row.get('mode', 'atomic'),
                        timestamp=row['timestamp']
                    )
                else:  # tool_response
                    import json
                    tool_responses = json.loads(row['tool_responses'])
                    entry = ToolsResponsePayload(
                        tool_responses=tool_responses,
                        content=row['content'],
                        timestamp=row['timestamp']
                    )
                entries.append(entry)
            except Exception as e:
                self.logger.warning(f"Failed to load entry from database: {e}")
                continue
        
        # Load entries into history (which will also handle context population)
        if entries:
            self.load_entries(entries)

    def update_history(self, entry: Union[MessagePayload, ToolsResponsePayload], token_estimate: int):
        """Update history with a new message or tool response."""
        if token_estimate > self.history_token_limit:
            raise ValueError(
                f"The token count ({token_estimate}) of the new entry exceeds the history limit ({self.history_token_limit})."
            )
            
        # Track entries to be deleted if persistence is enabled
        deleted_entries = []
        
        # Remove entries from history until the new entry will fit
        while (
            self.history_token_count + token_estimate >
            self.history_token_limit
        ):
            popped_entry, popped_token_count = self.history.popleft()
            self.history_token_count -= popped_token_count
            if self.persist:
                deleted_entries.append(popped_entry)

        self.history.append((entry, token_estimate))
        self.history_token_count += token_estimate
        
        # Update database if persistence is enabled
        if self.persist and (deleted_entries or entry):
            # Add to pending changes
            self._pending_deletes.extend(e.model.timestamp for e in deleted_entries)
            self._pending_inserts.append(entry)
            
            # Trigger database update
            loop = LoopRegistry.get_loop()
            loop.create_task(self._sync_database())

    async def _sync_database(self):
        """Synchronizes pending changes with the database in a single transaction."""
        if not self._pending_deletes and not self._pending_inserts:
            return

        # Get pending changes
        deletes = self._pending_deletes.copy()
        inserts = []
        for entry in self._pending_inserts:
            if isinstance(entry, MessagePayload):
                inserts.append({
                    "type": "message",
                    "role": entry.model.role,
                    "content": entry.model.content,
                    "mode": entry.model.mode,
                    "tool_responses": None,
                    "timestamp": entry.model.timestamp
                })
            else:  # ToolsResponsePayload
                import json
                # Filter out the 'call' key from tool_responses
                tool_responses = {k: v for k, v in entry.model.tool_responses.items() if k != 'call'}
                inserts.append({
                    "type": "tool_response",
                    "role": None,
                    "content": entry.model.content,
                    "mode": None,
                    "tool_responses": json.dumps(tool_responses),
                    "timestamp": entry.model.timestamp
                })
        
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
            self.logger.error(f"Error syncing database: {e}")

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

    def load_entries(self, entries: List[Union[MessagePayload, ToolsResponsePayload]]):
        """Batch load multiple messages and tool responses efficiently."""
        # Calculate token estimates for all entries first
        entry_tokens = []
        for entry in entries:
            if isinstance(entry, MessagePayload):
                token_estimate = get_token_len(entry.model.content, self.tokenizer_model)
            else:  # ToolsResponsePayload
                # Only count tokens if the tool has been called
                if not entry.model.tool_responses:
                    continue
                token_estimate = get_token_len(entry.model.content, self.tokenizer_model)
            entry_tokens.append((entry, token_estimate))
        
        # Update history and context in batch
        for entry, token_estimate in entry_tokens:
            self.update_history(entry, token_estimate)
            self.update_context(entry, token_estimate)
        
        # Trigger context update only once after all entries are processed
        self.param.trigger('context')

    def load_message(self, message: MessagePayload):
        """Load a single message. For backwards compatibility."""
        self.load_entries([message])

    def load_tool_response(self, tool_response: ToolsResponsePayload):
        """Load a single tool response."""
        if not tool_response.model.tool_responses:
            return
        self.load_entries([tool_response])

    def update_context(self, entry: Union[MessagePayload, ToolsResponsePayload], token_estimate: int):
        """Update context with a new message or tool response."""
        if token_estimate > self.context_token_limit:
            raise ValueError(
                f"The token count ({token_estimate}) of the new entry exceeds the context limit ({self.context_token_limit})."
            )
        while (
            self.context_token_count + token_estimate >
            self.context_token_limit
        ):
            popped_entry, popped_token_count = self.context.popleft()
            self.context_token_count -= popped_token_count

        self.context.append((entry, token_estimate))
        self.context_token_count += token_estimate

    def get_context_message_payloads(self) -> List[MessagePayload]:
        """Get all message payloads in the context window."""
        result = []
        for entry, _ in self.context:
            if isinstance(entry, MessagePayload):
                result.append(entry)
            elif isinstance(entry, ToolsResponsePayload):
                # Convert tool response into a MessagePayload for LLM context
                wrapper = MessagePayload(
                    role='assistant',
                    content=entry.model.content,
                    mode='atomic',
                    timestamp=entry.model.timestamp
                )
                result.append(wrapper)
        return result

    def get_context_tool_response_payloads(self) -> List[ToolsResponsePayload]:
        """Get all tool response payloads in the context window."""
        return [entry for entry, _ in self.context if isinstance(entry, ToolsResponsePayload)]

    def get_history_message_payloads(self) -> List[MessagePayload]:
        """Get all message payloads in the history."""
        result = []
        for entry, _ in self.history:
            if isinstance(entry, MessagePayload):
                result.append(entry)
            elif isinstance(entry, ToolsResponsePayload):
                # Convert tool response into a MessagePayload for historical log
                wrapper = MessagePayload(
                    role='assistant',
                    content=entry.model.content,
                    mode='atomic',
                    timestamp=entry.model.timestamp
                )
                result.append(wrapper)
        return result
        
    def get_history_tool_response_payloads(self) -> List[ToolsResponsePayload]:
        """Get all tool response payloads in the history."""
        return [entry for entry, _ in self.history if isinstance(entry, ToolsResponsePayload)]
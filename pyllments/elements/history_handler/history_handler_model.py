from collections import deque

import param

from pyllments.base.model_base import Model
from pyllments.common.tokenizers import get_token_len
from pyllments.payloads.message import MessagePayload


class HistoryHandlerModel(Model):

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

    def __init__(self, **params):
        super().__init__(**params)

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

    def update_history(self, message: MessagePayload, token_estimate: int):
        if token_estimate > self.history_token_limit:
            raise ValueError(
                f"The token count ({token_estimate}) of the new message exceeds the history limit ({self.history_token_limit})."
            )
        # Remove messages from history until the new message will fit
        while (
            self.history_token_count + token_estimate >
            self.history_token_limit
        ):
            popped_message, popped_token_count = self.history.popleft()
            self.history_token_count -= popped_token_count

        self.history.append((message, token_estimate))
        self.history_token_count += token_estimate

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
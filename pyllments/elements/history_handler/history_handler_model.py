from typing import List
from collections import deque

import param

from pyllments.base.model_base import Model
from pyllments.common import get_token_len
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

    tokenizer_model = param.String(default="gpt-4o-mini")
    new_message = param.ClassSelector(class_=MessagePayload)
    new_message_token_estimate = param.Integer(default=0, bounds=(0, None), doc="""
        The estimated token length of the new message""")

    def __init__(self, **params):
        super().__init__(**params)

    @param.depends('new_message', watch=True)
    def load_message(self) -> None:
        self.new_message_token_estimate = (
            self.new_message.model.get_token_len(self.tokenizer_model)
        )
        self.update_history()
        self.update_context()
        self.param.trigger('context')

    def update_history(self) -> None:
        if self.new_message_token_estimate > self.history_token_limit:
            raise ValueError(
                f"The token count ({self.new_message_token_estimate}) of the new message exceeds the history limit ({self.history_token_limit})."
            )
        # Remove messages from history until the new message will fit
        while (
            self.history_token_count + self.new_message_token_estimate >
            self.history_token_limit
        ):
            popped_message = self.history.popleft()
            popped_message_token_est = popped_message.model.tokenization_map.get(
                self.tokenizer_model,
                popped_message.model.get_token_len(self.tokenizer_model)
            )
            self.history_token_count -= popped_message_token_est

        self.history.append(self.new_message)
        self.history_token_count += self.new_message_token_estimate

    def update_context(self) -> None:
        if self.new_message_token_estimate > self.context_token_limit:
            raise ValueError(
                f"The token count ({self.new_message_token_estimate}) of the new message exceeds the context limit ({self.context_token_limit})."
            )
        while (
            self.context_token_count + self.new_message_token_estimate >
            self.context_token_limit
        ):
            popped_message = self.context.popleft()
            popped_message_token_est = popped_message.model.get_token_len(
                self.tokenizer_model
            )
            self.context_token_count -= popped_message_token_est

        self.context.append(self.new_message)
        self.context_token_count += self.new_message_token_estimate
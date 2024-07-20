import param
from typing import List


from pyllments.base.model_base import Model
from pyllments.payloads.message.message_model import MessageModel
from pyllments.common.tokenizers import get_token_len

class ContextBuilderModel(Model):
    max_tokens = param.Integer(default=4096, bounds=(1, None), doc="""
        The max amount of tokens to keep in the history""")
    tokens = param.Integer(default=0, bounds=(0, None), doc="""
        The amount of tokens to keep in the context window""")
    context = param.List(item_type=MessageModel, default=[])
    tokenizer_model = param.String(default="gpt-4o-mini")
    new_message = param.ClassSelector(class_=MessageModel)

    def __init__(self, **params):
        super().__init__(**params)

    def add_message(self, message: MessageModel) -> List[MessageModel]:
        self.context.append(message)
        return self.get_context_within_token_limit()

    def get_context_within_token_limit(self) -> List[MessageModel]:
        total_tokens = 0
        context_within_limit = []

        for message in reversed(self.context):
            message_tokens = len(self.tokenizer.encode(message.message.content))
            if total_tokens + message_tokens > self.max_tokens:
                break
            total_tokens += message_tokens
            context_within_limit.insert(0, message)

        return context_within_limit
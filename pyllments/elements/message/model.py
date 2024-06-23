from pyllments.base import Model

class MessageModel(Model):
    message = param.String(default=None, per_instance=True)
    message_type = param.String(default=None, per_instance=True)

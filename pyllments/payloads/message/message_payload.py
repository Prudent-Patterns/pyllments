import param
import panel as pn

from pyllments.base.payload_base import Payload
from pyllments.payloads.message.message_model import MessageModel

class MessagePayload(Payload):
    model = param.ClassSelector(class_=MessageModel, is_instance=True)
    message_type = param.String(default=None, per_instance=True)
    message_view = param.ClassSelector(class_=pn.pane.Markdown, is_instance=True)

    def create_message_view(self, **kwargs):
        self.message_view = pn.pane.Markdown(self.message)
        return self.message_view

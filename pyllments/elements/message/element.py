import param
import panel as pn

from pyllments.base import Element

class MessageElement(Element):
    message = param.String(default=None, per_instance=True)
    message_type = param.String(default=None, per_instance=True)
    message_view = param.ClassSelector(class_=pn.pane.Markdown, is_instance=True)

    def create_message_view(self, **kwargs):
        self.message_view = pn.pane.Markdown(self.message)
        return self.message_view
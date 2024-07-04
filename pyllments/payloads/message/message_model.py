import warnings

import param

from pyllments.base.model_base import Model

class MessageModel(Model):
    message_type = param.String(default=None, instantiate=True)
    message_text = param.String(default='', instantiate=True)
    mode = param.Selector(
        objects=['atomic', 'stream'],
        allow_refs=True,
        default='atomic',
        instantiate=True
        )
    stream_obj = param.Parameter(default=None, instantiate=True)

    def stream(self):
        # TODO Needs async implementation
        if self.mode != 'stream':
            warnings.warn('Mode is not set to stream')
            return
        else:
            for seg in self.stream_obj:
                self.message_text += seg
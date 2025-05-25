import param
from loguru import logger as _default_logger

class Model(param.Parameterized):
    logger = param.Parameter(default=None, doc="Logger instance for this model")

    def __init__(self, **params):
        super().__init__(**params)
        if self.logger:
            self.logger = self.logger.bind(name=self.__class__.__module__)
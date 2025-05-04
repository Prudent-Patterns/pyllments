import param
from loguru import logger as _default_logger

class Model(param.Parameterized):
    logger = param.Parameter(default=_default_logger, doc="Logger instance for this model")

    def __init__(self, **params):
        super().__init__(**params)
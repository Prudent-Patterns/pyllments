import param
from loguru import logger as _default_logger


class Model(param.Parameterized):
    """
    Base for element and payload models.

    Elements forward their whole ``**params`` to their model, so by default
    unknown keys are dropped. A payload model is built by callers with explicit
    keyword arguments, where a misspelled key is a bug; those models set
    ``strict_params = True`` and reject keys they do not declare.
    """

    logger = param.Parameter(default=None, doc="Logger instance for this model")

    strict_params = False

    def __init__(self, **params):
        known_params = {key: value for key, value in params.items() if key in self.param}
        if self.strict_params:
            unknown = sorted(set(params) - set(known_params))
            if unknown:
                raise TypeError(
                    f"{type(self).__name__} got unknown parameter(s): {', '.join(unknown)}"
                )
        super().__init__(**known_params)
        if self.logger:
            self.logger = self.logger.bind(name=self.__class__.__module__)

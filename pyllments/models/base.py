import param

class Model(param.Parameterized):
    def __init__(self, **params):
        super().__init__(**params)
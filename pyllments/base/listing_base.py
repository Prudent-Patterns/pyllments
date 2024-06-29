import param

class Listing(param.Parameterized):
    def __init__(self, **params):
        super().__init__(**params)

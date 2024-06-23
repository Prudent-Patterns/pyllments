from langchain_core.language_models import BaseLanguageModel

from pyllments.base import Model

class LLMChatModel(Model):
    model_class = param.ClassSelector(
        class_=BaseLanguageModel,
        is_instance=False,
        doc='Class of a LangChain Chat Model',
        default=ChatOpenAI
    )
    model_args = param.ClassSelector(
        class_=(dict, list), #TODO: May replace with dict, as the elements will the logic for view creation
        doc='''Takes a dictionary of arguments to pass to expose and send to the
        model class. If you set a None value as the key, the argument will be exposed,
        with the default value set. Passing a list is the same as passing a dict
        with all values set to None.''',
        is_instance=True,
        default={}
        )

    model = param.ClassSelector(class_=BaseLanguageModel, default=None, pickle_default_value=False)

    def __init__(self, **params):
        super().__init__(**params)

        self._set_params()
        self._create_model()

    def _set_params(self):
        """Sets specified model_args as params of the object"""
        if self.model_args:
            for arg, val in self.model_args.items():
                if arg in self.model_class.__fields__:
                    if val is None:
                        default = self.model_class.__fields__[arg].default
                        self.model_args[arg] = default
                        self.param.add_parameter(arg, param.Parameter(default, per_instance=True))
                    else:
                        self.param.add_parameter(arg, param.Parameter(val, per_instance=True))
                    # self.model_args_list.append(arg)
                else:
                    raise ValueError(f"'{arg}' is missing from the model class's signature")
                self.param.watch(self._create_model, [*self.model_args.keys()])


    def _create_model(self, event=None):
        """Creates the model instance on init and when any of the parameters change"""
        arg_vals = {arg: self.param.values()[arg] for arg in self.model_args.keys()}
        self.model = self.model_class(**arg_vals)

    def stream(self, messages):
        # TODO: Set it up to be async
        return self.model.stream(messages)

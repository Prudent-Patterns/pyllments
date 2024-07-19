import param

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages.base import BaseMessage

from pyllments.base.model_base import Model


class LLMChatModel(Model):
    chat_model = param.ClassSelector(class_=BaseLanguageModel, doc="""
        Instance of active chat model.""")

    model_args = param.Dict(default={}, doc="""
        Takes a dictionary of arguments to pass to expose and send to the
        model class. If you set a None value as the key, the argument will be exposed,
        with the default value set. Passing a list is the same as passing a dict
        with all values set to None.""") # TODO Allow nested dict for model_name: model_args format
    
    provider_name = param.String(default='openai', doc='Provider of the model')
    model_name = param.String(default='gpt-3.5-turbo', doc='Name of the model')
    incoming_messages = param.List(item_type=BaseMessage)
    output_mode = param.Selector(
        objects=['atomic', 'stream'],
        default='stream',
        )
    # new_message = param.ClassSelector(class_=AIMessage)
    outgoing_message = param.Parameter(doc="""
        AIMessage or Stream, depending on output_mode""")

    def __init__(self, **params):
        super().__init__(**params)
        self._initialize_provider()
        self._initialize_model()
        # self._set_params()
    #     self._create_watchers()

    # def _create_watchers(self):
    #     self.param.watch(
    #         self._new_outgoing_message,
    #         'outgoing_message',
    #         onlychanged=False
    #         )
    # def _set_params(self):
    #     """Sets specified model_args as params of the object"""
    #     if self.model_args:
    #         for arg, val in self.model_args.items():
    #             if arg in self.model_class.__fields__:
    #                 if val is None:
    #                     default = self.model_class.__fields__[arg].default
    #                     self.model_args[arg] = default
    #                     self.param.add_parameter(arg, param.Parameter(default, per_instance=True))
    #                 else:
    #                     self.param.add_parameter(arg, param.Parameter(val, per_instance=True))
    #                 # self.model_args_list.append(arg)
    #             else:
    #                 raise ValueError(f"'{arg}' is missing from the model class's signature")
    #             self.param.watch(self._create_model, [*self.model_args.keys()])


    # def _create_model(self, event=None):
    #     """Creates the model instance on init and when any of the parameters change"""
    #     arg_vals = {arg: self.param.values()[arg] for arg in self.model_args.keys()}
    #     self.model = self.model_class(**arg_vals)
    
    def _initialize_provider(self):
        """Initializes the provider"""
        match self.provider_name:
            case 'openai':
                from langchain_openai import ChatOpenAI
                self.provider = ChatOpenAI
            case 'anthropic':
                from langchain_anthropic import ChatAnthropic
                self.provider = ChatAnthropic
            case 'groq':
                from langchain_groq import ChatGroq
                self.provider = ChatGroq
            case 'mistral':
                from langchain_mistralai import ChatMistralAI
                self.provider = ChatMistralAI
            case 'google':
                from langchain_google_genai import ChatGoogleGenerativeAI
                self.provider = ChatGoogleGenerativeAI
            case _:
                raise ValueError(f"Provider name '{self.provider_name}' is not valid")

    def _initialize_model(self):
        """Initializes the model"""
        self.chat_model = self.provider(model_name=self.model_name, **self.model_args)
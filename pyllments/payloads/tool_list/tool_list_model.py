from typing import Literal, Union

import jinja2
import param
from pydantic import BaseModel, create_model, Field

from pyllments.base.model_base import Model


class ToolListModel(Model):
    tool_list = param.List(default=[], doc="""
        [{
            'name': 'mcp_name_tool_name',
            'description': 'Tool description',
            'parameters': {
                'type': 'object',
                'properties': {'property': {'type': 'string'}},
        },]
        """)
    content = param.Parameter(default=None, doc="""
        Tool list schema""")

    template = param.ClassSelector(default=None, class_=jinja2.Template)
    tool_format = param.Selector(default='default', objects=['default', 'verbose'], doc="""
        The format of the tool list.
        'default':
            - weather.get_weather(location: string)
            - todo.add_task(task: string)
        'verbose':
            """)
    schema = param.ClassSelector(default=None, class_=BaseModel)

    def __init__(self, **params):
        super().__init__(**params)
        self.schema = self.schema_setup(self.tool_list)

    def get_template_str(self):
        if self.tool_format == 'default':
            return self.jinja_env.get_template('default.jinja')
    
    def schema_setup(self, tool_list):
        tool_models = [self.create_tool_model(tool) for tool in tool_list]
        self.schema = create_model('', tools=(Union[*tool_models], ...))

    def create_tool_model(tool):
        model_args = {}
        model_args['name'] = (Literal[tool['name']], ...)
        if properties := tool['parameters'].get('properties'):
            model_args['parameters'] = (object, Field(json_schema_extra=properties))
        model_args['__doc__'] = tool.description
        model_args['__base__'] = CleanModel


        tool_model = create_model(
            tool.name,
            **model_args
        )
        return tool_model


class CleanModel(BaseModel):
    @classmethod
    def remove_titles_recursively(cls,obj):
        if isinstance(obj, dict):
            if "title" in obj:
                del obj["title"]
            for value in obj.values():
                cls.remove_titles_recursively(value)
        elif isinstance(obj, list):
            for item in obj:
                cls.remove_titles_recursively(item)

    model_config = {
        "json_schema_extra": lambda schema, model: model.remove_titles_recursively(schema)
    }

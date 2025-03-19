from pydantic import BaseModel


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

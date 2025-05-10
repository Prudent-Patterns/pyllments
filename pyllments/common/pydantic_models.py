from pydantic import BaseModel
from pydantic.config import ConfigDict


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

    # Use ConfigDict to attach a JSON schema hook that strips titles recursively
    model_config = ConfigDict(
        json_schema_extra=lambda schema, model: CleanModel.remove_titles_recursively(schema)
    )

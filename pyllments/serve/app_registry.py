from fastapi import FastAPI


class AppRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.app = None
        return cls._instance
    
    @classmethod
    def get_app(cls):
        if cls._instance is None or cls._instance.app is None:
            instance = cls()
            instance.app = FastAPI()
        return cls._instance.app
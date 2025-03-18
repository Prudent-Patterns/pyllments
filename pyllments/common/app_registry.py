from fastapi import FastAPI


class AppRegistry:
    """
    A simple registry to maintain a single shared FastAPI app instance.
    """
    _app: FastAPI = None

    @classmethod
    def get_app(cls) -> FastAPI:
        """
        Returns a shared FastAPI app instance.
        If not created yet, it creates and stores a new FastAPI instance.
        """
        if cls._app is None:
            cls._app = FastAPI()
        return cls._app
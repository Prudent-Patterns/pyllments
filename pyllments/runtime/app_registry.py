from fastapi import FastAPI
# Import necessary components
from contextlib import asynccontextmanager
from loguru import logger
from pyllments.runtime.lifecycle_manager import manager as lifecycle_manager

# Define the lifespan context manager
@asynccontextmanager
async def pyllments_lifespan(app: FastAPI):
    # Code to run on startup (optional)
    logger.info("Pyllments FastAPI Lifespan: Startup")
    yield
    # Code to run on shutdown
    logger.info("Pyllments FastAPI Lifespan: Shutdown initiated. Cleaning up resources...")
    try:
        await lifecycle_manager.shutdown()
        logger.info("Pyllments FastAPI Lifespan: Resource cleanup complete.")
    except Exception as e:
        logger.error(f"Pyllments FastAPI Lifespan: Error during resource cleanup: {e}")

class AppRegistry:
    """
    A simple registry to maintain a single shared FastAPI app instance.
    Automatically adds a lifespan manager for resource cleanup.
    """
    _app: FastAPI = None

    @classmethod
    def get_app(cls) -> FastAPI:
        """
        Returns a shared FastAPI app instance.
        If not created yet, it creates and stores a new FastAPI instance
        with the pyllments_lifespan manager included.
        """
        if cls._app is None:
            logger.info("Creating new FastAPI app instance with Pyllments lifespan manager.")
            # Create the app with the lifespan manager
            cls._app = FastAPI(lifespan=pyllments_lifespan)
        return cls._app
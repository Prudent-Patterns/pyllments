import asyncio

class LoopRegistry:
    """
    Provides access to the application-wide asyncio event loop.
    This class is responsible only for retrieving or creating the loop.
    """
    _loop = None

    @classmethod
    def get_loop(cls):
        """
        Retrieves the current event loop.

        If a loop is already running, it is returned. If not, a new event loop is created
        and set as the default before returning it.
        """
        if cls._loop is None:
            try:
                cls._loop = asyncio.get_running_loop()  # Returns if running.
            except RuntimeError:
                cls._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(cls._loop)
        return cls._loop
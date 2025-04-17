import asyncio
from loguru import logger

class LoopRegistry:
    """
    Singleton for managing the application-wide asyncio event loop.
    Provides a centralized way to get or create an event loop.
    """
    _loop = None

    @classmethod
    def get_loop(cls):
        """
        Get the event loop, creating one if necessary.
        
        Returns
        -------
        asyncio.AbstractEventLoop
            The event loop instance.
        """
        # Return cached loop if we have one
        if cls._loop is not None:
            logger.debug(f"LoopRegistry: Using cached loop {id(cls._loop)}")
            return cls._loop
            
        # Try to get the existing loop or create a new one
        policy = asyncio.get_event_loop_policy()
        try:
            cls._loop = policy.get_event_loop()
            if cls._loop is None or cls._loop.is_closed():
                cls._loop = policy.new_event_loop()
                policy.set_event_loop(cls._loop)
                logger.debug(f"LoopRegistry: Created new loop {id(cls._loop)}")
            else:
                logger.debug(f"LoopRegistry: Using existing loop {id(cls._loop)}")
        except RuntimeError:
            cls._loop = policy.new_event_loop()
            policy.set_event_loop(cls._loop)
            logger.debug(f"LoopRegistry: Created new loop {id(cls._loop)}")
        return cls._loop
    
    @classmethod
    def reset(cls):
        """
        Reset the singleton loop reference.
        Useful for testing scenarios.
        """
        if cls._loop is not None and cls._loop.is_running():
            logger.warning("Resetting a running loop - this may cause issues")
            
        cls._loop = None
        logger.debug("LoopRegistry: Reset loop reference")

    @classmethod
    def set(cls, loop):
        """
        Set the singleton loop reference.
        """
        cls._loop = loop
        logger.debug(f"LoopRegistry: Set loop reference to {id(cls._loop)}")

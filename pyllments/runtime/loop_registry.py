import asyncio
from loguru import logger


class LoopRegistry:
    """
    Bound runtime loop for Pyllments-owned processes.

    Embedded hosts and pytest-asyncio should provide the running loop; this
    registry only caches or creates a loop when Pyllments explicitly owns the
    runtime (serve, headless recipes, sync test drivers).
    """

    _loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_loop(cls) -> asyncio.AbstractEventLoop:
        """
        Return the bound runtime loop, preferring a running loop when present.

        Returns
        -------
        asyncio.AbstractEventLoop
            The event loop instance.
        """
        if cls._loop is not None and not cls._loop.is_closed():
            return cls._loop

        try:
            cls._loop = asyncio.get_running_loop()
            return cls._loop
        except RuntimeError:
            pass

        policy = asyncio.get_event_loop_policy()
        if cls._loop is None or cls._loop.is_closed():
            cls._loop = policy.new_event_loop()
            policy.set_event_loop(cls._loop)
            logger.debug("LoopRegistry: Created new loop {}", id(cls._loop))
        return cls._loop

    @classmethod
    def reset(cls) -> None:
        """Clear the bound loop reference (tests and runtime teardown)."""
        if cls._loop is not None and cls._loop.is_running():
            logger.warning("Resetting a running loop - this may cause issues")
        cls._loop = None
        logger.debug("LoopRegistry: Reset loop reference")

    @classmethod
    def set(cls, loop: asyncio.AbstractEventLoop) -> None:
        """Bind Pyllments to an externally owned loop (tests, embedded apps)."""
        cls._loop = loop
        logger.debug("LoopRegistry: Set loop reference to {}", id(cls._loop))

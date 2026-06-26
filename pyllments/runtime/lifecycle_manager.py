import asyncio
import weakref

from loguru import logger


class LifecycleManager:
    """Tracks long-lived resources that require explicit shutdown."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._active_resources = weakref.WeakSet()
        self._shutdown_started = asyncio.Event()
        self._initialized = True
        logger.trace("LifecycleManager initialized (resource shutdown only).")

    @classmethod
    def reset_for_tests(cls) -> None:
        """Reset singleton state for test isolation."""
        instance = cls._instance
        if instance is None:
            return
        instance._active_resources = weakref.WeakSet()
        instance._shutdown_started = asyncio.Event()

    @staticmethod
    def _resource_label(resource) -> str:
        name = getattr(resource, "name", None)
        if name is not None:
            return f"resource {resource.__class__.__name__}({name})"
        return f"resource {resource!r}"

    def _log_gather_errors(self, results, labels):
        """Log exceptions from asyncio.gather(..., return_exceptions=True)."""
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.warning("LifecycleManager error during {}: {}", label, result)

    def register_resource(self, resource) -> None:
        """
        Register a generic resource for shutdown.

        Resource should implement ``close`` (sync or async).
        """
        logger.trace("Registering resource {} for cleanup.", resource)
        self._active_resources.add(resource)

    async def shutdown(self) -> None:
        """Close all registered resources."""
        if self._shutdown_started.is_set():
            logger.trace("Shutdown already called.")
            return

        self._shutdown_started.set()

        tasks = []
        task_labels = []
        resources_to_close = list(self._active_resources)
        logger.trace("Closing {} active resources...", len(resources_to_close))

        errors = 0
        for resource in resources_to_close:
            if resource is None:
                continue
            close_fn = getattr(resource, "close", None)
            label = self._resource_label(resource)
            if not callable(close_fn):
                continue
            if asyncio.iscoroutinefunction(close_fn):
                logger.trace("Adding {} to close tasks.", label)
                tasks.append(close_fn())
                task_labels.append(f"close of {label}")
            else:
                try:
                    logger.trace("Closing {} synchronously.", label)
                    close_fn()
                except Exception as exc:
                    errors += 1
                    logger.warning("LifecycleManager error during close of {}: {}", label, exc)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._log_gather_errors(results, task_labels)
            errors += sum(1 for result in results if isinstance(result, Exception))

        logger.info(
            "LifecycleManager shutdown complete: {} resources closed, {} errors encountered.",
            len(resources_to_close),
            errors,
        )


manager = LifecycleManager()

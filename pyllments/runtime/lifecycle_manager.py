import asyncio
import weakref

from loguru import logger


class LifecycleManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LifecycleManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._active_output_ports = weakref.WeakSet()
        self._active_resources = weakref.WeakSet()
        self._shutdown_started = asyncio.Event()
        self._initialized = True
        logger.trace("LifecycleManager initialized (async drain/shutdown only).")

    @classmethod
    def reset_for_tests(cls):
        """
        Reset singleton state for test isolation.

        Clears registries and allows shutdown to run again. Does not replace
        the singleton instance; use a fresh manager only when tests need a
        separate LifecycleManager class.
        """
        instance = cls._instance
        if instance is None:
            return
        instance._active_output_ports = weakref.WeakSet()
        instance._active_resources = weakref.WeakSet()
        instance._shutdown_started = asyncio.Event()

    @staticmethod
    def _port_label(port) -> str:
        name = getattr(port, "name", None)
        port_id = getattr(port, "id", None)
        if name is not None and port_id is not None:
            return f"port {name} ({port_id})"
        return repr(port)

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
                logger.warning(f"LifecycleManager error during {label}: {result}")

    def register_port(self, port):
        """Register an OutputPort for shutdown (and optional bulk drain)."""
        logger.trace(f"Registering port {port.name} ({port.id}) for cleanup.")
        self._active_output_ports.add(port)

    def register_resource(self, resource):
        """
        Register a generic resource for shutdown.

        Resource should implement ``close`` (sync or async).
        """
        logger.trace(f"Registering resource {resource} for cleanup.")
        self._active_resources.add(resource)

    def _drainable_ports(self):
        ports = [p for p in list(self._active_output_ports) if p is not None]
        return [
            p for p in ports
            if hasattr(p, "drain") and asyncio.iscoroutinefunction(getattr(p, "drain"))
        ]

    async def drain_all_ports(self):
        """
        Wait until all registered output ports have flushed their emission queues.

        Prefer ``await output_port.drain()`` on specific ports when you know
        which emissions must complete. This bulk helper is mainly for shutdown
        and tests.
        """
        drainables = self._drainable_ports()
        if not drainables:
            return
        labels = [self._port_label(p) for p in drainables]
        results = await asyncio.gather(
            *(p.drain() for p in drainables), return_exceptions=True
        )
        self._log_gather_errors(results, [f"drain of {label}" for label in labels])

    async def drain(self):
        """Alias for :meth:`drain_all_ports` (backward compatible)."""
        await self.drain_all_ports()

    async def shutdown(self):
        """Drain queues, then close all registered output ports and resources."""
        if self._shutdown_started.is_set():
            logger.trace("Shutdown already called.")
            return

        self._shutdown_started.set()

        logger.trace("Draining registered output ports before shutdown...")
        await self.drain_all_ports()

        tasks = []
        task_labels = []
        ports_to_close = list(self._active_output_ports)
        logger.trace(f"Closing {len(ports_to_close)} active output ports...")

        errors = 0
        for port in ports_to_close:
            if port is not None and hasattr(port, "close") and asyncio.iscoroutinefunction(port.close):
                label = self._port_label(port)
                logger.trace(f"Adding {label} to close tasks.")
                tasks.append(port.close())
                task_labels.append(f"close of {label}")
            else:
                logger.trace("Skipping already collected or invalid port reference.")

        resources_to_close = list(self._active_resources)
        logger.trace(f"Closing {len(resources_to_close)} active resources...")
        for resource in resources_to_close:
            if resource is not None:
                close_fn = getattr(resource, "close", None)
                label = self._resource_label(resource)
                if callable(close_fn):
                    if asyncio.iscoroutinefunction(close_fn):
                        logger.trace(f"Adding {label} to close tasks.")
                        tasks.append(close_fn())
                        task_labels.append(f"close of {label}")
                    else:
                        try:
                            logger.trace(f"Closing {label} synchronously.")
                            close_fn()
                        except Exception as e:
                            errors += 1
                            logger.warning(f"LifecycleManager error during close of {label}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._log_gather_errors(results, task_labels)
            errors += sum(1 for r in results if isinstance(r, Exception))

        logger.info(
            f"LifecycleManager shutdown complete: {len(ports_to_close)} ports closed, "
            f"{errors} errors encountered."
        )


# Instantiate the singleton
manager = LifecycleManager()

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

    def register_port(self, port):
        """Register an OutputPort for drain/shutdown."""
        logger.trace(f"Registering port {port.name} ({port.id}) for cleanup.")
        self._active_output_ports.add(port)

    def register_resource(self, resource):
        """
        Register a generic resource for shutdown.

        Resource should implement ``close`` (sync or async).
        """
        logger.trace(f"Registering resource {resource} for cleanup.")
        self._active_resources.add(resource)

    async def drain(self):
        """
        Wait until all registered output ports have flushed their emission queues.

        This does not stop emission tasks. Use before returning from short-lived
        handlers or before shutdown when delivery completion is required.
        """
        ports = [p for p in list(self._active_output_ports) if p is not None]
        drainables = [
            p for p in ports
            if hasattr(p, "drain") and asyncio.iscoroutinefunction(getattr(p, "drain"))
        ]
        if not drainables:
            return
        await asyncio.gather(*(p.drain() for p in drainables), return_exceptions=True)


    async def shutdown(self):
        """Close all registered output ports and resources."""
        if self._shutdown_started.is_set():
            logger.trace("Shutdown already called.")
            return

        self._shutdown_started.set()

        tasks = []
        ports_to_close = list(self._active_output_ports)
        logger.trace(f"Closing {len(ports_to_close)} active output ports...")

        errors = 0
        for port in ports_to_close:
            if port is not None and hasattr(port, 'close') and asyncio.iscoroutinefunction(port.close):
                logger.trace(f"Adding port {port.name} ({port.id}) to close tasks.")
                tasks.append(port.close())
            else:
                logger.trace("Skipping already collected or invalid port reference.")

        resources_to_close = list(self._active_resources)
        logger.trace(f"Closing {len(resources_to_close)} active resources...")
        for resource in resources_to_close:
            if resource is not None:
                close_fn = getattr(resource, 'close', None)
                if callable(close_fn):
                    if asyncio.iscoroutinefunction(close_fn):
                        logger.trace(f"Adding resource {resource} to close tasks.")
                        tasks.append(close_fn())
                    else:
                        try:
                            logger.trace(f"Closing resource {resource} synchronously.")
                            close_fn()
                        except Exception as e:
                            errors += 1
                            logger.trace(f"Error during resource close: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                    logger.trace(f"Error during port close: {result}")
        logger.info(f"LifecycleManager shutdown complete: {len(ports_to_close)} ports closed, {errors} errors encountered.")

# Instantiate the singleton
manager = LifecycleManager()

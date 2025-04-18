import asyncio
import signal
import weakref
import atexit
from loguru import logger
from pyllments.common.loop_registry import LoopRegistry

class LifecycleManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LifecycleManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization
        if self._initialized:
            return
        self._active_output_ports = weakref.WeakSet()
        self._shutdown_started = asyncio.Event()
        self._install_signal_handlers()
        self._initialized = True
        # Register the atexit handler
        atexit.register(self._atexit_cleanup)
        logger.trace("LifecycleManager initialized and atexit handler registered.")

    def register_port(self, port):
        """Register an OutputPort for cleanup."""
        logger.trace(f"Registering port {port.name} ({port.id}) for cleanup.")
        self._active_output_ports.add(port)

    def _signal_handler(self, sig):
        """Internal handler to trigger async shutdown."""
        logger.trace(f"Received signal {sig.name}. Initiating graceful shutdown...")
        # Use call_soon_threadsafe as signal handlers run in the main thread
        try:
            loop = LoopRegistry.get_loop()
            if loop.is_running():
                 loop.call_soon_threadsafe(self._schedule_shutdown)
            else:
                 logger.trace("Loop not running, cannot schedule graceful shutdown via signal.")
        except Exception as e:
             logger.trace(f"Error scheduling shutdown from signal handler: {e}")

    def _schedule_shutdown(self):
         """Schedules the shutdown coroutine if not already started."""
         # Check if shutdown already started to prevent scheduling multiple times
         if not self._shutdown_started.is_set(): 
              logger.trace("Scheduling shutdown task.")
              try:
                   loop = LoopRegistry.get_loop()
                   if loop.is_running():
                        # Create task in the existing loop
                        asyncio.create_task(self.shutdown())
                   else:
                        # Fallback: Run in a new loop if main loop is stopped
                        logger.trace("Main loop stopped, running shutdown in new temporary loop.")
                        try:
                            asyncio.run(self.shutdown())
                        except RuntimeError as e:
                            # Avoid errors if asyncio.run is called recursively or loop policies conflict
                            logger.trace(f"Could not run shutdown in new loop (possibly nested asyncio.run): {e}")
              except Exception as e:
                   logger.trace(f"Error creating shutdown task: {e}")
         else:
              logger.trace("Shutdown already in progress or scheduled.")

    def _atexit_cleanup(self):
        """Synchronous cleanup function registered with atexit."""
        logger.trace("atexit cleanup triggered.")
        # Check if shutdown hasn't already been successfully run
        if not self._shutdown_started.is_set():
            logger.trace("Shutdown not initiated gracefully, attempting synchronous cleanup via atexit.")
            # We MUST run the async shutdown synchronously here.
            # Try getting the loop, but expect it might be closed.
            try:
                loop = LoopRegistry.get_loop()
                if loop.is_running():
                    logger.trace("atexit: Loop still running, trying to run shutdown_sync_via_loop.")
                    # Try to run to completion if loop is running
                    # This is still risky as the loop might close under us
                    future = asyncio.run_coroutine_threadsafe(self.shutdown(), loop)
                    future.result(5) # Add a timeout
                    logger.trace("atexit: Shutdown completed via run_coroutine_threadsafe.")
                else:
                    logger.trace("atexit: Loop is closed, running shutdown in new temporary loop via asyncio.run().")
                    # Fallback: run in a new loop (most common case for atexit during exception)
                    asyncio.run(self.shutdown())
                    logger.trace("atexit: Shutdown completed via asyncio.run().")
            except Exception as e:
                # Catch errors during the atexit cleanup attempt
                logger.trace(f"Error during atexit cleanup: {e}. Some resources may not be released.")
        else:
            logger.trace("atexit: Shutdown already started/completed gracefully.")

    def _install_signal_handlers(self):
        """Attempt to install signal handlers for graceful shutdown."""
        try:
            loop = LoopRegistry.get_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                # Check if a handler is already set (don't overwrite user handlers)
                # Note: This check might not be perfectly reliable across all scenarios.
                current_handler = signal.getsignal(sig)
                if current_handler is signal.SIG_DFL or current_handler is None: # Default or no handler
                     # loop.add_signal_handler only works reliably on POSIX
                     if hasattr(loop, 'add_signal_handler'):
                          loop.add_signal_handler(sig, self._signal_handler, sig)
                          logger.trace(f"Installed signal handler for {sig.name}.")
                     else:
                          logger.trace(f"Loop does not support add_signal_handler (likely Windows). Cannot install handler for {sig.name}.")
                # elif current_handler != signal.SIG_IGN: # Check if not ignored
                #     logger.warning(f"Signal handler already set for {sig.name}. Skipping installation.")

        except ValueError:
             logger.trace("Cannot install signal handlers in non-main thread.")
        except NotImplementedError:
             logger.trace("Signal handling not implemented for this event loop policy.")
        except Exception as e:
             logger.trace(f"Failed to install signal handlers: {e}")


    async def shutdown(self):
        """Perform graceful shutdown of registered resources."""
        if self._shutdown_started.is_set():
            logger.trace("Shutdown already called.")
            return

        self._shutdown_started.set() # Mark shutdown as started

        tasks = []
        ports_to_close = list(self._active_output_ports) # Iterate over a copy
        logger.trace(f"Closing {len(ports_to_close)} active output ports...")

        errors = 0
        for port in ports_to_close:
            # Check if the weakref is still valid
            if port is not None and hasattr(port, 'close') and asyncio.iscoroutinefunction(port.close):
                logger.trace(f"Adding port {port.name} ({port.id}) to close tasks.")
                tasks.append(port.close())
            else:
                 logger.trace(f"Skipping already collected or invalid port reference.")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                    logger.trace(f"Error during port close: {result}")
        # Final summary log at info level for visibility
        logger.info(f"LifecycleManager shutdown complete: {len(ports_to_close)} ports closed, {errors} errors encountered.")

# Instantiate the singleton
manager = LifecycleManager()

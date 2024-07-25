import sys
from loguru import logger

def setup_logging(
        log_file=None, stdout_log_level="DEBUG",
        file_log_level="DEBUG", file_log_mode='w'):
    logger.enable("pyllments")

    logger.remove()
    
    # Adding stdout logging with formatted time and level for better alignment
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {message}"
    logger.add(sys.stdout, level=stdout_log_level, format=log_format, enqueue=True)
    
    if log_file:
        # Apply the same format to the log file
        logger.add(
            log_file, rotation="10 MB", level=file_log_level,
            format=log_format, mode=file_log_mode, enqueue=True)

    return logger

def log_staging(element: object, port_name: str, item_name: str, item_value: any):
    """
    Logs the clean Element type, port name, and the name and type of the staged item.

    Args:
        element (object): The element instance being logged.
        port_name (str): The name of the port associated with the element.
        item_name (str): The name of the staged item.
        item_value (any): The value of the staged item.
    """
    # Get the class name of the element to log its type
    element_type = element.__class__.__name__
    
    # Get the type of the staged item
    item_type = type(item_value).__name__
    
    # Log the information in a single line
    logger.info(f"Staging: {element_type} | {port_name} | Staged Item: {item_name}: {item_type}")

def log_emit(element: object, port_name: str, payload: object):
    """
    Logs the emission of a payload from an element, including the element type,
    port name, and the type of the payload.

    Args:
        element (object): The element instance emitting the payload.
        port_name (str): The name of the port associated with the element.
        payload (object): The payload being emitted.
    """
    # Get the class name of the element to log its type
    element_type = element.__class__.__name__
    
    # Log the information in a single line
    logger.info(f"Emitting from {element_type} | Port: {port_name} | Payload: {type(payload).__name__}")

def log_receive(element: object, port_name: str, payload: object):
    """
    Logs the reception of a payload by an element, including the element type,
    port name, and the type of the received payload.

    Args:
        element (object): The element instance receiving the payload.
        port_name (str): The name of the port associated with the element.
        payload (object): The payload being received.
    """
    # Get the class name of the element to log its type
    element_type = element.__class__.__name__
    
    # Log the information in a single line
    logger.info(f"Receiving in {element_type} | Port: {port_name} | Payload: {type(payload).__name__}")

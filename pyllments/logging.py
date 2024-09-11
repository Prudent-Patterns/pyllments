import sys
from loguru import logger

def setup_logging(
        log_file=None, stdout_log_level="DEBUG",
        file_log_level="DEBUG", file_log_mode='w'):
    logger.enable("pyllments")

    logger.remove()
    
    # Adding stdout logging with formatted time and level for better alignment
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:^8}</level> | {message}"
    logger.add(sys.stdout, level=stdout_log_level, format=log_format, enqueue=True)
    
    if log_file:
        # Apply the same format to the log file
        logger.add(
            log_file, rotation="10 MB", level=file_log_level,
            format=log_format, mode=file_log_mode, enqueue=True)

    return logger

def log_staging(port: object, item_name: str, item_value: any):
    """
    Logs the clean Element type, port name, and the name and type of the staged item.

    Args:
        element (object): The element instance being logged.
        port_name (str): The name of the port associated with the element.
        item_name (str): The name of the staged item.
        item_value (any): The value of the staged item.
    """
    # Get the class name of the element to log its type
    element_type = port.containing_element.__class__.__name__
    
    # Get the type of the staged item
    item_type = type(item_value).__name__
    
    # Log the information in a single line
    logger.info(f"Staging: {element_type} | Port: {port.name} | Staged Item: {item_name}: {item_type}")

def log_emit(port: object, payload: object):
    """
    Logs the emission of a payload from an element, including the element type,
    port name, and the type of the payload.

    Args:
        port (object): The port instance emitting the payload.
        payload (object): The payload being emitted.
    """
    # Get the class name of the element to log its type
    element_type = port.containing_element.__class__.__name__
    
    # Log the information in a single line
    logger.info(f"Emitting from {element_type} | Port: {port.name} | Payload: {type(payload).__name__}")

def log_receive(port: object, payload: object):
    """
    Logs the reception of a payload by an element, including the element type,
    port name, and the type of the received payload.

    Args:
        port (object): The port instance receiving the payload.
        payload (object): The payload being received.
    """
    # Get the class name of the element to log its type
    element_type = port.containing_element.__class__.__name__
    
    # Log the information in a single line
    logger.info(f"Receiving in {element_type} | Port: {port.name} | Payload: {type(payload).__name__}")

def log_connect(output_port: object, input_port: object):
    """
    Logs the connection of an input port to an output port, including the element type,
    port name, and the type of the input port.
    """
    # Get the class name of the element to log its type
    output_element_type = output_port.containing_element.__class__.__name__
    input_element_type = input_port.containing_element.__class__.__name__
    
    # Log the information in a single line
    logger.info(f"Connecting {input_element_type} | Port: {input_port.name} to {output_element_type} | Port: {output_port.name}")

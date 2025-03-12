#!/usr/bin/env python3
"""
Simple MCP (Model Context Protocol) Server Example
This server demonstrates the core MCP capabilities:
- Tools: Functions that can be called by the LLM
- Resources: File-like data that can be read by clients
- Prompts: Pre-written templates to help users accomplish tasks
"""

from mcp.server.fastmcp import FastMCP
import datetime
import random

# Create an MCP server with a name
mcp = FastMCP("Demo MCP Server")

# ---- TOOLS ----
@mcp.tool()
def calculate(operation: str, a: float, b: float) -> str:
    """
    Perform a mathematical operation on two numbers.
    
    Args:
        operation: One of 'add', 'subtract', 'multiply', 'divide'
        a: First number
        b: Second number
        
    Returns:
        Result of the operation as a string
    """
    operations = {
        'add': lambda x, y: x + y,
        'subtract': lambda x, y: x - y,
        'multiply': lambda x, y: x * y,
        'divide': lambda x, y: x / y if y != 0 else "Error: Division by zero"
    }
    
    if operation not in operations:
        return f"Error: Unknown operation '{operation}'. Use add, subtract, multiply, or divide."
    
    try:
        result = operations[operation](a, b)
        return f"Result of {a} {operation} {b} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_current_time() -> str:
    """Get the current date and time."""
    now = datetime.datetime.now()
    return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"

@mcp.tool()
def generate_random_number(min_value: int = 1, max_value: int = 100) -> int:
    """
    Generate a random number between min_value and max_value (inclusive).
    
    Args:
        min_value: Minimum value (default: 1)
        max_value: Maximum value (default: 100)
        
    Returns:
        A random integer
    """
    return random.randint(min_value, max_value)

# ---- RESOURCES ----
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """
    Get a personalized greeting for a name.
    
    Args:
        name: The name to greet
        
    Returns:
        A personalized greeting
    """
    return f"Hello, {name}! Welcome to the MCP server."

@mcp.resource("weather://current")
def get_weather() -> str:
    """Get the current weather (simulated)."""
    conditions = ["Sunny", "Cloudy", "Rainy", "Snowy", "Windy"]
    temperatures = range(0, 35)
    
    condition = random.choice(conditions)
    temperature = random.choice(temperatures)
    
    return f"Current weather: {condition}, {temperature}°C"

@mcp.resource("help://commands")
def get_help() -> str:
    """Get help information about available commands."""
    return """
    Available MCP Commands:
    
    Tools:
    - calculate: Perform math operations (add, subtract, multiply, divide)
    - get_current_time: Get the current date and time
    - generate_random_number: Generate a random number
    
    Resources:
    - greeting://{name}: Get a personalized greeting
    - weather://current: Get current weather information
    - help://commands: Show this help information
    
    Prompts:
    - weather-report: Generate a weather report
    - introduction: Generate an introduction
    """

# ---- PROMPTS ----
@mcp.prompt()
def weather_report(location: str) -> str:
    """
    Generate a prompt for a weather report.
    
    Args:
        location: The location to get weather for
        
    Returns:
        A prompt for generating a weather report
    """
    return f"""Please generate a detailed weather report for {location}.
    Include temperature, precipitation, wind conditions, and a 3-day forecast.
    Also mention any severe weather alerts if applicable."""

@mcp.prompt()
def introduction(topic: str, audience: str) -> str:
    """
    Generate a prompt for an introduction on a topic.
    
    Args:
        topic: The topic to introduce
        audience: The target audience (e.g., beginners, experts)
        
    Returns:
        A prompt for generating an introduction
    """
    return f"""Please write an introduction to {topic} for an audience of {audience}.
    The introduction should be clear, engaging, and appropriate for the knowledge level of the audience.
    Include key concepts and why this topic is important."""

# Run the server when executed directly
if __name__ == "__main__":
    mcp.run(transport='stdio')

"""
# Simple MCP Server Example

This is a simple demonstration of a Model Context Protocol (MCP) server in Python. It showcases the core MCP capabilities:

- **Tools**: Functions that can be called by the LLM
- **Resources**: File-like data that can be read by clients
- **Prompts**: Pre-written templates to help users accomplish tasks

## Setup

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Run the MCP server:

```bash
python mcp_server.py
```

## Features

### Tools

The server provides the following tools:

- `calculate`: Perform mathematical operations (add, subtract, multiply, divide)
- `get_current_time`: Get the current date and time
- `generate_random_number`: Generate a random number between specified values

### Resources

The server provides the following resources:

- `greeting://{name}`: Get a personalized greeting
- `weather://current`: Get current weather information (simulated)
- `help://commands`: Show help information about available commands

### Prompts

The server provides the following prompt templates:

- `weather_report`: Generate a prompt for a weather report
- `introduction`: Generate a prompt for an introduction on a topic

## Usage Examples

### Using Tools

```python
# Calculate the sum of two numbers
result = mcp.call_tool("calculate", operation="add", a=5, b=3)
print(result)  # "Result of 5 add 3 = 8"

# Get the current time
time = mcp.call_tool("get_current_time")
print(time)  # "Current time: 2023-04-01 12:34:56"

# Generate a random number
number = mcp.call_tool("generate_random_number", min_value=1, max_value=10)
print(number)  # A random number between 1 and 10
```

### Using Resources

```python
# Get a personalized greeting
greeting = mcp.get_resource("greeting://Alice")
print(greeting)  # "Hello, Alice! Welcome to the MCP server."

# Get current weather
weather = mcp.get_resource("weather://current")
print(weather)  # "Current weather: Sunny, 25°C"

# Get help information
help_info = mcp.get_resource("help://commands")
print(help_info)  # Shows available commands
```

### Using Prompts

```python
# Get a weather report prompt
weather_prompt = mcp.get_prompt("weather_report", location="New York")
print(weather_prompt)  # A prompt for generating a weather report for New York

# Get an introduction prompt
intro_prompt = mcp.get_prompt("introduction", topic="Machine Learning", audience="beginners")
print(intro_prompt)  # A prompt for generating an introduction to Machine Learning for beginners
```

## Extending the Server

You can extend this server by adding more tools, resources, and prompts. Simply follow the patterns shown in the code.
"""
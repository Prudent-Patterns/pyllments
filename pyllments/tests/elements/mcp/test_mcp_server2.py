#!/usr/bin/env python3
"""
Simple MCP (Model Context Protocol) Server Example 2
This server demonstrates additional MCP capabilities with different tools
than the original example server.
"""

from mcp.server.fastmcp import FastMCP
import datetime
import random
import string

# Create an MCP server with a name
mcp = FastMCP("Demo MCP Server 2")

# ---- TOOLS ----
@mcp.tool()
def format_text(text: str, format_type: str) -> str:
    """
    Format text according to specified type.
    
    Args:
        text: Text to format
        format_type: One of 'uppercase', 'lowercase', 'title', 'reverse'
        
    Returns:
        Formatted text as a string
    """
    formats = {
        'uppercase': lambda x: x.upper(),
        'lowercase': lambda x: x.lower(),
        'title': lambda x: x.title(),
        'reverse': lambda x: x[::-1]
    }
    
    if format_type not in formats:
        return f"Error: Unknown format '{format_type}'. Use uppercase, lowercase, title, or reverse."
    
    try:
        result = formats[format_type](text)
        return f"Formatted text ({format_type}): {result}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_timestamp(timezone: str = "UTC") -> str:
    """Get the current timestamp in specified timezone."""
    now = datetime.datetime.now()
    return f"Timestamp ({timezone}): {now.isoformat()}"

@mcp.tool()
def generate_password(length: int = 12, include_special: bool = True) -> str:
    """
    Generate a random password.
    
    Args:
        length: Password length (default: 12)
        include_special: Include special characters (default: True)
        
    Returns:
        A random password string
    """
    chars = string.ascii_letters + string.digits
    if include_special:
        chars += string.punctuation
    
    return ''.join(random.choice(chars) for _ in range(length))

# ---- RESOURCES ----
@mcp.resource("quote://random")
def get_quote() -> str:
    """Get a random inspirational quote."""
    quotes = [
        "Be the change you wish to see in the world.",
        "The only way to do great work is to love what you do.",
        "Innovation distinguishes between a leader and a follower.",
        "Stay hungry, stay foolish."
    ]
    return random.choice(quotes)

@mcp.resource("status://system")
def get_status() -> str:
    """Get system status (simulated)."""
    statuses = ["Healthy", "Warning", "Critical"]
    metrics = {
        "cpu": random.randint(0, 100),
        "memory": random.randint(0, 100),
        "disk": random.randint(0, 100)
    }
    
    status = random.choice(statuses)
    return f"System Status: {status}\nMetrics: {metrics}"

# Run the server when executed directly
if __name__ == "__main__":
    mcp.run(transport='stdio')

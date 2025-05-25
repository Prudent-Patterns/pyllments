"""
Core type utilities for the pyllments library.

This module contains type conversion and validation utilities that are used
across different parts of the codebase without creating circular dependencies.
"""

from typing import Any, Dict


class TypeMapper:
    """
    Utility class for consistent type string to Python type mapping across the codebase.
    """
    # Standard type mappings used throughout the system
    TYPE_MAPPINGS = {
        "int": int, 
        "float": float, 
        "bool": bool, 
        "str": str,
        "dict": dict,
        "list": list
    }
    
    @classmethod
    def string_to_type(cls, type_str: str) -> type:
        """
        Convert a type string to the corresponding Python type.
        
        For CLI compatibility, some types are mapped to str:
        - dict types become str (to be parsed as JSON later)
        - list types become str (to be parsed later)
        
        Parameters
        ----------
        type_str : str
            String representation of the type (e.g., "int", "str", "bool")
            
        Returns
        -------
        type
            The corresponding Python type
        """
        if isinstance(type_str, type):
            return type_str
        
        if isinstance(type_str, str):
            normalized = type_str.lower()
            
            # Special handling for complex types that CLI can't handle directly
            if normalized.startswith("dict") or normalized == "dict":
                return str  # CLI will accept as JSON string
            elif normalized.startswith("list") or normalized == "list":
                return str  # CLI will accept as comma-separated or JSON string
            
            return cls.TYPE_MAPPINGS.get(normalized, str)  # Default to str for unknown types
        
        return str  # Fallback for any other case

    @classmethod
    def is_dict_type(cls, type_str: str) -> bool:
        """
        Check if a type string represents a dictionary type.
        
        Parameters
        ----------
        type_str : str
            Type string to check
            
        Returns
        -------
        bool
            True if the type string represents a dict type
        """
        if isinstance(type_str, str):
            return type_str.lower().startswith("dict")
        return False 
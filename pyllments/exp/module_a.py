from pathlib import Path
import sys

class A:
    def __init__(self):
        self.patha = Path(__file__)

    # @classmethod
    # def get_rel_path(cls):
    #     """Gets the path of the class calling it"""
    #     return Path(cls.__file__)
    
    @classmethod
    def get_base_path(cls):
        # Get the module where the class is defined
        module = sys.modules[cls.__module__]
        # Return the parent directory of the module's file
        return Path(module.__file__)
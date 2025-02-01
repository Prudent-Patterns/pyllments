"""CLI module for pyllments."""
from .state import app

__all__ = ['app']


def main():
    app()
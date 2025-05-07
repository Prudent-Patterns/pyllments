"""CLI module for pyllments."""
from .app import app

__all__ = ['app']


def main():
    app()
"""
veloctra_core/__init__.py
=========================
Core configuration & base abstractions for Veloctra Data Platform.
"""

from veloctra_core.settings import get_settings, Settings

__version__ = "1.0.0"
__all__ = ["get_settings", "Settings"]

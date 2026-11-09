"""Derive HealthDCAT-AP catalogue records from REDCap project metadata.

The library exists so the CLI stays testable; it is not the user interface.
"""

__version__ = "0.1.0"

from .config import Config
from .model import Project, Variable

__all__ = ["Config", "Project", "Variable", "__version__"]

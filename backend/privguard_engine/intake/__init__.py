"""Intake: decide whether an uploaded file can be processed, and make names safe.

Framework-free (D-002): nothing here imports Django.
"""

from .filetypes import INTAKE_VERSION, Inspection, Verdict, inspect_file, supported_extensions
from .names import UnsafePath, clean_display_text, display_name, safe_relative_path

__all__ = [
    "INTAKE_VERSION",
    "Inspection",
    "UnsafePath",
    "Verdict",
    "clean_display_text",
    "display_name",
    "inspect_file",
    "safe_relative_path",
    "supported_extensions",
]

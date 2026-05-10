#!/usr/bin/env python3
"""Deprecated: use 'avm audit-prospect <domain>' instead.

This script forwards to avm.prereqs for backward compatibility.
The new audit-prospect command covers all prereqs checks plus five
additional scoring categories and a consultant-ready report.
"""
import sys
import warnings

warnings.warn(
    "prereqs_sweep.py is deprecated. Use 'avm audit-prospect <domain>' instead.",
    DeprecationWarning,
    stacklevel=1,
)

from avm.prereqs import main_cli

if __name__ == "__main__":
    sys.exit(main_cli())

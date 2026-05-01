#!/usr/bin/env python3
"""Run a citation check on your domain. See README for setup."""
import sys
from avm.citation import main_cli

if __name__ == "__main__":
    sys.exit(main_cli())

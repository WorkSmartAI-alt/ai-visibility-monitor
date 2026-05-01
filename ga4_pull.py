#!/usr/bin/env python3
"""Pull Google Analytics 4 data. See README for setup."""
import sys
from avm.ga4 import main_cli

if __name__ == "__main__":
    sys.exit(main_cli())

#!/usr/bin/env python3
"""Pull Google Search Console data. See README for setup."""
import sys
from avm.gsc import main_cli

if __name__ == "__main__":
    sys.exit(main_cli())

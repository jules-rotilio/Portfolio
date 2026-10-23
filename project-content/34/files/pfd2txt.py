#!/usr/bin/env python3
"""Show a Drakkar Valkyrie VCFG profile (.pfd) in human-readable form.

Usage: pfd2txt.py [--json] FILE.pfd [FILE.pfd ...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from valkyrie.pfd import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())

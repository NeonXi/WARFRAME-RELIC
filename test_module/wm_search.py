"""
WARFRAME-RELIC Test Module - WM Item Search & Price Query

Entry point for the application.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_window import main

if __name__ == "__main__":
    main()
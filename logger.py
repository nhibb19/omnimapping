"""
OmniMapping Logging Configuration
Provides structured logging for the platform.
"""

import logging
import sys
from pathlib import Path

from config import PROJECT_ROOT

# Create logs directory
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure logger
logger = logging.getLogger('omnimapping')
logger.setLevel(logging.INFO)

# Remove any existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(LOGS_DIR / "omnimapping.log")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logger.getChild(name)

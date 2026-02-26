# CLIMARISK-OG Backend __init__.py
# Package initialization

__version__ = "0.2.0"
__author__ = "vitoralves82"
__description__ = "CLIMARISK-OG — Climate Risk Pricing Platform (offshore)"

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

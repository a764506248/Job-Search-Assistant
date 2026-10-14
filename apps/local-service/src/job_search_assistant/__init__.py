import os

__version__ = os.getenv("JSA_APP_VERSION", "0.4.31").removeprefix("v")

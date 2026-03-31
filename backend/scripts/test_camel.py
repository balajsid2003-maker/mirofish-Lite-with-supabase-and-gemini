import sys
import os
try:
    from camel.types import ModelPlatformType
    print([m.name for m in ModelPlatformType])
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")

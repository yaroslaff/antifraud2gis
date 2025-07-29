import random
from pathlib import Path
import os
from typing import Optional
import inspect

from .settings import settings

def random_file(path: Path) -> Optional[Path]:
    path = Path(path)
    chosen = None
    count = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                count += 1
                if random.randint(1, count) == 1:
                    chosen = Path(entry.path)
    return chosen

def caller(depth=3):
    PROJECT_ROOT = os.path.dirname(__file__)
    stack = inspect.stack()[1:1+depth]
    parts = []
    for frame in reversed(stack):
        relpath = os.path.relpath(frame.filename, PROJECT_ROOT)
        parts.append(f"{relpath}:{frame.lineno} in {frame.function}()")
    return " → ".join(parts)

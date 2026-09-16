"""IMU 3Dビジュアライザ エントリポイント.

使い方:
    python3 src/viewer3d/main.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.viewer3d.server import run

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

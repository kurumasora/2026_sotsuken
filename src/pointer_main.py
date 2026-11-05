"""
ポインタ表示エントリポイント（デバッグ用）．

BLE から IMU データを受信し，roll/pitch を画面上のドットとして表示する．

使い方:
    uv run src/pointer_main.py              # EMA ON、β=0.1
    uv run src/pointer_main.py --no-ema     # EMA OFF、β=0.1
    uv run src/pointer_main.py --beta 0.05  # EMA ON、β=0.05
"""

import argparse
import asyncio
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import ble_receiver, display

_QUEUE_MAXSIZE = 5


def main() -> None:
    parser = argparse.ArgumentParser(description="AccelPointer（デバッグ用ポインタ表示）")
    parser.add_argument("--no-ema", action="store_true", help="EMAフィルタを無効化する")
    parser.add_argument("--beta", type=float, default=None, help="Madgwickフィルタのβ値")
    args = parser.parse_args()

    beta = args.beta if args.beta is not None else 0.1
    ema_enabled = not args.no_ema

    data_queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
    ble_loop_holder: list[asyncio.AbstractEventLoop] = []
    ble_stop_holder: list[asyncio.Event] = []

    def ble_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        ble_loop_holder.append(loop)
        ble_stop_holder.append(stop_event)
        try:
            loop.run_until_complete(ble_receiver.run(data_queue, stop_event))
        except Exception as e:
            print(f"BLEエラー: {e}")
        finally:
            loop.close()

    t = threading.Thread(target=ble_thread, daemon=True)
    t.start()

    try:
        display.run(data_queue, ema_enabled=ema_enabled, beta=beta)
    except KeyboardInterrupt:
        pass
    finally:
        if ble_loop_holder and ble_stop_holder:
            ble_loop_holder[0].call_soon_threadsafe(ble_stop_holder[0].set)
        t.join(timeout=3.0)


if __name__ == "__main__":
    main()

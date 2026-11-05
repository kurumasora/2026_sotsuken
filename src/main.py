"""
AccelPointer エントリポイント.

使い方:
    python src/main.py           # EMA ON（デフォルト）
    python src/main.py --no-ema  # EMA OFF
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
    parser = argparse.ArgumentParser(description="AccelPointer")
    parser.add_argument("--no-ema", action="store_true", help="EMAフィルタを無効化する")
    args = parser.parse_args()

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
        display.run(data_queue, ema_enabled=not args.no_ema)
    except KeyboardInterrupt:
        pass
    finally:
        # BLEスレッドに停止を通知して正常終了を待つ
        if ble_loop_holder and ble_stop_holder:
            ble_loop_holder[0].call_soon_threadsafe(ble_stop_holder[0].set)
        t.join(timeout=3.0)


if __name__ == "__main__":
    main()

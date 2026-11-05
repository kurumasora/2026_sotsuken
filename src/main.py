"""
キーマップシステム — OS入力モード エントリポイント．

ドウェルタイムで確定したキーを pynput 経由で OS のキーボード入力として送信する．

【初回実行前に必要な設定（macOS）】
  システム設定 → プライバシーとセキュリティ → アクセシビリティ
  → ターミナル（またはPython）を許可

使い方:
    uv run src/main.py              # EMA ON、β=0.1
    uv run src/main.py --no-ema     # EMA OFF
    uv run src/main.py --beta 0.05  # β値指定

デバッグ（ターミナル出力のみ）:
    uv run src/keymap_debug.py

ポインタ表示（デバッグ）:
    uv run src/pointer_main.py
"""

import argparse
import asyncio
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pynput.keyboard import Controller, Key

from src import ble_receiver
from src.keymap import keymap_display

_QUEUE_MAXSIZE = 5

_KB = Controller()
_SPECIAL: dict[str, Key] = {
    "SPC": Key.space,
    "BS":  Key.backspace,
    "ENT": Key.enter,
    "TAB": Key.tab,
}


def _send(key: str) -> None:
    k = _SPECIAL.get(key)
    if k is not None:
        _KB.press(k)
        _KB.release(k)
    else:
        _KB.type(key)


def main() -> None:
    parser = argparse.ArgumentParser(description="AccelPointer キーマップ（OS入力）")
    parser.add_argument("--no-ema", action="store_true", help="EMAフィルタを無効化する")
    parser.add_argument("--beta", type=float, default=None, help="Madgwickフィルタのβ値")
    args = parser.parse_args()

    beta        = args.beta if args.beta is not None else 0.1
    ema_enabled = not args.no_ema

    data_queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
    ble_loop_holder: list[asyncio.AbstractEventLoop] = []
    ble_stop_holder: list[asyncio.Event]             = []

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
        keymap_display.run(
            data_queue,
            ema_enabled=ema_enabled,
            beta=beta,
            dwell_ms=500,
            on_confirm=_send,
        )
    except KeyboardInterrupt:
        pass
    finally:
        if ble_loop_holder and ble_stop_holder:
            ble_loop_holder[0].call_soon_threadsafe(ble_stop_holder[0].set)
        t.join(timeout=3.0)


if __name__ == "__main__":
    main()

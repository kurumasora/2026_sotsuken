"""BLE → Madgwick → WebSocket で四元数をブラウザに送信するサーバー.

起動:
    python3 src/viewer3d/main.py
"""

import asyncio
import json
import os
import struct
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import websockets
from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.madgwick import MadgwickFilter

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID")
DEVICE_NAME         = os.getenv("DEVICE_NAME")
WS_PORT   = 8765
HTTP_PORT = 8080
HTML_DIR  = Path(__file__).resolve().parent

_clients: set = set()
_madgwick = MadgwickFilter(beta=0.1, sample_rate=30.0)


async def _ws_handler(websocket, path=None):
    _clients.add(websocket)
    print(f"ブラウザ接続 (計 {len(_clients)} クライアント)")
    try:
        await websocket.wait_closed()
    finally:
        _clients.discard(websocket)


async def _ble_loop(imu_queue: asyncio.Queue) -> None:
    print(f"'{DEVICE_NAME}' をスキャン中...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )
    if device is None:
        print(f"デバイス '{DEVICE_NAME}' が見つかりませんでした.")
        return

    print(f"接続: {device.name} ({device.address})")

    def handler(sender, data: bytearray) -> None:
        if len(data) == 24:
            try:
                imu_queue.put_nowait(struct.unpack("<ffffff", data))
            except asyncio.QueueFull:
                pass

    async with BleakClient(device) as client:
        await client.start_notify(CHARACTERISTIC_UUID, handler)
        print("IMUデータ受信中... (Ctrl+C で終了)")
        await asyncio.Future()


async def _process_loop(imu_queue: asyncio.Queue) -> None:
    while True:
        ax, ay, az, gx, gy, gz = await imu_queue.get()
        _madgwick.update(ax, ay, az, gx, gy, gz)
        q0, q1, q2, q3 = _madgwick.quaternion

        if _clients:
            msg = json.dumps({"q0": q0, "q1": q1, "q2": q2, "q3": q3})
            await asyncio.gather(
                *[c.send(msg) for c in list(_clients)],
                return_exceptions=True,
            )


def _start_http_server() -> None:
    os.chdir(HTML_DIR)
    server = HTTPServer(("localhost", HTTP_PORT), SimpleHTTPRequestHandler)
    print(f"HTTP server: http://localhost:{HTTP_PORT}/index.html")
    server.serve_forever()


async def run() -> None:
    threading.Thread(target=_start_http_server, daemon=True).start()
    await asyncio.sleep(0.3)
    webbrowser.open(f"http://localhost:{HTTP_PORT}/index.html")

    imu_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    async with websockets.serve(_ws_handler, "localhost", WS_PORT):
        print(f"WebSocket server: ws://localhost:{WS_PORT}")
        await asyncio.gather(
            _ble_loop(imu_queue),
            _process_loop(imu_queue),
        )

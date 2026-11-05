"""BLE経由で6軸IMUデータ（24バイト）を受信してキューに流す."""

import asyncio
import os
import queue
import struct
from pathlib import Path

from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID")
DEVICE_NAME = os.getenv("DEVICE_NAME")


async def run(data_queue: queue.Queue, stop_event: asyncio.Event) -> None:
    print(f"'{DEVICE_NAME}' をスキャン中...")

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )
    if device is None:
        print(f"デバイス '{DEVICE_NAME}' が見つかりませんでした.")
        stop_event.set()
        return

    print(f"接続: {device.name} ({device.address})")

    def handler(sender, data: bytearray) -> None:
        if len(data) == 24:
            values = struct.unpack("<ffffff", data) #24バイトで送信（0-11: ax, zy, az /12-23: gx, gy, gz ）
            if data_queue.full():
                try:
                    data_queue.get_nowait()
                except queue.Empty:
                    pass
            data_queue.put_nowait(values)

    async with BleakClient(device) as client:
        await client.start_notify(CHARACTERISTIC_UUID, handler)
        print("受信中. Ctrl+C またはウィンドウを閉じると終了.")
        try:
            await stop_event.wait()
        finally:
            await client.stop_notify(CHARACTERISTIC_UUID)

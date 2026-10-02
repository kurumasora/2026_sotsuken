"""
Nano 33 IoTからBLE経由で6軸IMUデータを受信し,CSVに保存するスクリプト.

保存列:
    time_s [s], ax, ay, az [g], gx, gy, gz [deg/s],
    vx, vy, vz [m/s]  … 加速度を1重積分
    px, py, pz [m]    … 加速度を2重積分（重力込みのためドリフトあり）
    rx, ry, rz [deg]  … 角速度を積分

事前準備:
    pip install bleak

使い方:
    python ble_accel_logger.py
"""
from dotenv import load_dotenv
import os
import asyncio
import struct
import csv
import time
from pathlib import Path
from bleak import BleakScanner, BleakClient

load_dotenv()

SERVICE_UUID        = os.getenv('SERVICE_UUID')
CHARACTERISTIC_UUID = os.getenv('CHARACTERISTIC_UUID')
DEVICE_NAME         = os.getenv('DEVICE_NAME')

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CSV_FILENAME = DATA_DIR / f"accel_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"

DT       = 1.0 / 30.0   # センサのサンプリング間隔 [s]
G_TO_MS2 = 9.80665       # [m/s²/g]

CSV_HEADER = [
    "time_s",
    "ax", "ay", "az",          # 加速度 [g]
    "gx", "gy", "gz",          # 角速度 [deg/s]
    "vx", "vy", "vz",          # 速度 [m/s]   （加速度1重積分）
    "px", "py", "pz",          # 位置 [m]     （加速度2重積分）
    "rx", "ry", "rz",          # 回転角 [deg] （角速度積分）
]


def notification_handler(csv_writer):
    """BLEのnotifyを受け取るたびに呼ばれるコールバック関数を返す（6軸24バイト）."""
    vel      = [0.0, 0.0, 0.0]
    pos      = [0.0, 0.0, 0.0]
    angle    = [0.0, 0.0, 0.0]
    start_time = None

    def handler(sender, data: bytearray):
        nonlocal start_time
        if len(data) != 24:
            print(f"想定外のデータ長です: {len(data)} bytes")
            return

        now = time.monotonic()
        if start_time is None:
            start_time = now
        elapsed = now - start_time

        ax, ay, az, gx, gy, gz = struct.unpack("<ffffff", data)

        # 積分
        for i, a in enumerate((ax, ay, az)):
            vel[i] += a * G_TO_MS2 * DT
            pos[i] += vel[i] * DT
        for i, g in enumerate((gx, gy, gz)):
            angle[i] += g * DT

        print(
            f"t={elapsed:8.3f}s"
            f"  A=({ax:+.3f},{ay:+.3f},{az:+.3f})"
            f"  G=({gx:+.6f},{gy:+.6f},{gz:+.6f})"
            f"  P=({pos[0]:+.4f},{pos[1]:+.4f},{pos[2]:+.4f})"
            f"  R=({angle[0]:+.2f},{angle[1]:+.2f},{angle[2]:+.2f})"
        )
        csv_writer.writerow([
            round(elapsed, 4),
            ax, ay, az,
            gx, gy, gz,
            *vel,
            *pos,
            *angle,
        ])

    return handler


async def main():
    print("Nano 33 IoT (AccelSensor) をスキャン中...")

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )

    if device is None:
        print(f"デバイス '{DEVICE_NAME}' が見つかりませんでした.")
        print("Arduino側の電源が入っているか,アドバタイズ中か確認してください.")
        return

    print(f"デバイスが見つかりました: {device.name} ({device.address})")

    with open(CSV_FILENAME, mode="w", newline="", encoding="utf-8") as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(CSV_HEADER)

        async with BleakClient(device) as client:
            print(f"接続しました. Ctrl+C で終了します. 保存先: {CSV_FILENAME}")

            await client.start_notify(
                CHARACTERISTIC_UUID, notification_handler(csv_writer)
            )

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n終了処理中...")
            finally:
                await client.stop_notify(CHARACTERISTIC_UUID)

    print(f"CSVファイルに保存しました: {CSV_FILENAME}")


if __name__ == "__main__":
    asyncio.run(main())
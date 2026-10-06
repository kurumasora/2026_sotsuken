"""
3種類の姿勢推定手法を比較するCSVロガー.

比較手法:
  1. ジャイロ積分のみ  : gx/gy/gz を積分してロール・ピッチ・ヨーを推定
  2. 加速度のみ        : φ = atan2(ay, az) でロール，θ = atan2(-ax, √(ay²+az²)) でピッチを推定
                        (yawは重力では推定不可)
  3. Madgwickフィルタ  : 上記2つを融合した四元数フィルタ

BLE接続して6軸データを受信し，同じフレームから3手法を同時計算してCSVに保存.

出力先: ~/myo2/data/comparison_YYYYMMDD_HHMMSS/comparison.csv

使い方:
    cd ~/myo2
    python datalogger/compare_methods.py
"""
from dotenv import load_dotenv
import os
import asyncio
import struct
import csv
import time
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.madgwick import MadgwickFilter
from bleak import BleakScanner, BleakClient

load_dotenv()

CHARACTERISTIC_UUID = os.getenv('CHARACTERISTIC_UUID')
DEVICE_NAME         = os.getenv('DEVICE_NAME')

DATA_BASE = Path.home() / "myo2" / "data"

DT      = 1.0 / 30.0
RAD2DEG = 180.0 / math.pi

CSV_HEADER = [
    "time_s",
    # 生センサデータ
    "ax", "ay", "az",                          # [g]
    "gx", "gy", "gz",                          # [deg/s]
    # 手法1: ジャイロ積分
    "gyro_roll", "gyro_pitch", "gyro_yaw",     # [deg]
    # 手法2: 加速度のみ
    "accel_roll", "accel_pitch",               # [deg]  yawは重力のみでは推定不可
    # 手法3: Madgwickフィルタ
    "madgwick_roll", "madgwick_pitch", "madgwick_yaw",  # [deg]
]


def quat_to_euler(q0, q1, q2, q3):
    """四元数 (w=q0, x=q1, y=q2, z=q3) → ZYX オイラー角 (roll, pitch, yaw) [deg]."""
    roll  = math.atan2(2*(q0*q1 + q2*q3), 1 - 2*(q1*q1 + q2*q2)) * RAD2DEG
    pitch = math.asin(max(-1.0, min(1.0, 2*(q0*q2 - q3*q1))))    * RAD2DEG
    yaw   = math.atan2(2*(q0*q3 + q1*q2), 1 - 2*(q2*q2 + q3*q3)) * RAD2DEG
    return roll, pitch, yaw


def notification_handler(csv_writer, madgwick):
    """BLE notifyコールバックを返す（6軸24バイト）."""
    # 手法1: ジャイロ積分の状態
    gyro_angle = [0.0, 0.0, 0.0]   # roll, pitch, yaw [deg]
    start_time = None

    def handler(sender, data: bytearray):
        nonlocal start_time
        if len(data) != 24:
            print(f"想定外のデータ長: {len(data)} bytes")
            return

        now = time.monotonic()
        if start_time is None:
            start_time = now
        elapsed = now - start_time

        ax, ay, az, gx, gy, gz = struct.unpack("<ffffff", data)

        # ── 手法1: ジャイロ積分 ──────────────────────────────
        gyro_angle[0] += gx * DT   # roll
        gyro_angle[1] += gy * DT   # pitch
        gyro_angle[2] += gz * DT   # yaw

        # ── 手法2: 加速度のみ ────────────────────────────────
        # φ = atan2(ay, az)   … ロール（X軸まわり）
        # θ = atan2(-ax, √(ay²+az²)) … ピッチ（Y軸まわり）
        accel_roll  = math.atan2(ay, az) * RAD2DEG
        accel_pitch = math.atan2(-ax, math.sqrt(ay*ay + az*az)) * RAD2DEG

        # ── 手法3: Madgwickフィルタ ─────────────────────────
        madgwick.update(ax, ay, az, gx, gy, gz)
        q0, q1, q2, q3 = madgwick.quaternion
        mw_roll, mw_pitch, mw_yaw = quat_to_euler(q0, q1, q2, q3)

        print(
            f"t={elapsed:8.3f}s"
            f"  Gyro=({gyro_angle[0]:+7.2f},{gyro_angle[1]:+7.2f},{gyro_angle[2]:+7.2f})"
            f"  Accel=({accel_roll:+7.2f},{accel_pitch:+7.2f},   ---)"
            f"  Madgwick=({mw_roll:+7.2f},{mw_pitch:+7.2f},{mw_yaw:+7.2f})"
        )
        csv_writer.writerow([
            round(elapsed, 4),
            ax, ay, az,
            gx, gy, gz,
            *[round(v, 4) for v in gyro_angle],
            round(accel_roll, 4), round(accel_pitch, 4),
            round(mw_roll, 4), round(mw_pitch, 4), round(mw_yaw, 4),
        ])

    return handler


async def main():
    print(f"'{DEVICE_NAME}' をスキャン中...")

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )
    if device is None:
        print(f"デバイス '{DEVICE_NAME}' が見つかりませんでした.")
        print("Arduino側の電源とアドバタイズを確認してください.")
        return

    print(f"デバイスが見つかりました: {device.name} ({device.address})")

    out_dir = DATA_BASE / f"comparison_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "comparison.csv"

    madgwick = MadgwickFilter(beta=0.1, sample_rate=30.0)

    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)

        async with BleakClient(device) as client:
            print(f"接続しました. Ctrl+C で終了. 保存先: {csv_path}")
            print("列: gyro_roll/pitch/yaw | accel_roll/pitch | madgwick_roll/pitch/yaw  [deg]")

            await client.start_notify(
                CHARACTERISTIC_UUID, notification_handler(writer, madgwick)
            )
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n終了処理中...")
            finally:
                await client.stop_notify(CHARACTERISTIC_UUID)

    print(f"CSVを保存しました: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())

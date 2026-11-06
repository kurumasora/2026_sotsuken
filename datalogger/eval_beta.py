"""
Madgwickフィルタのβ値評価用CSVロガー．

指定したβ値でセンサデータを取得し，姿勢角・ポインタ位置をCSVに記録する．
複数のβ値で計測して比較することでチューニングに使用する．

評価観点:
  - 静止時: roll/pitch/px/pyの分散が小さい → 安定（ドリフト少）
  - 動作時: 応答の素早さ（別途グラフで確認）

出力先: data/eval_beta/beta{値}_YYYYMMDD_HHMMSS.csv

使い方:
    cd sotsuken-2026
    uv run datalogger/eval_beta.py --beta 0.05
    uv run datalogger/eval_beta.py --beta 0.1
    uv run datalogger/eval_beta.py --beta 0.2
"""
import argparse
import asyncio
import csv
import math
import os
import struct
import sys
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.madgwick import MadgwickFilter

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID")
DEVICE_NAME         = os.getenv("DEVICE_NAME")

SAMPLE_RATE  = 30.0
DT           = 1.0 / SAMPLE_RATE
MAX_ROLL_DEG  = 45.0
MAX_PITCH_DEG = 30.0

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "eval_beta"

CSV_HEADER = [
    "time_s",
    "ax", "ay", "az",       # 加速度 [g]
    "gx", "gy", "gz",       # 角速度 [deg/s]
    "roll", "pitch",         # Madgwick姿勢角 [deg]
    "px", "py",              # 正規化ポインタ位置 [-1, 1]
]


def quat_to_roll_pitch(q0, q1, q2, q3):
    roll  = math.atan2(2*(q0*q1 + q2*q3), 1 - 2*(q1*q1 + q2*q2))
    pitch = math.asin(max(-1.0, min(1.0, 2*(q0*q2 - q3*q1))))
    return math.degrees(roll), math.degrees(pitch)


def make_handler(csv_writer, madgwick):
    start_time = None

    def handler(sender, data: bytearray):
        nonlocal start_time
        if len(data) != 24:
            return
        now = time.monotonic()
        if start_time is None:
            start_time = now
        elapsed = now - start_time

        ax, ay, az, gx, gy, gz = struct.unpack("<ffffff", data)
        madgwick.update(ax, ay, az, gx, gy, gz)
        q0, q1, q2, q3 = madgwick.quaternion

        roll, pitch = quat_to_roll_pitch(q0, q1, q2, q3)
        px = -roll  / MAX_ROLL_DEG
        py = -pitch / MAX_PITCH_DEG

        print(
            f"t={elapsed:7.3f}s"
            f"  roll={roll:+7.2f}°  pitch={pitch:+7.2f}°"
            f"  px={px:+.3f}  py={py:+.3f}"
        )
        csv_writer.writerow([
            round(elapsed, 4),
            ax, ay, az, gx, gy, gz,
            round(roll, 4), round(pitch, 4),
            round(px, 4), round(py, 4),
        ])

    return handler


async def main(beta: float):
    print(f"β={beta} で評価計測を開始します")
    print(f"'{DEVICE_NAME}' をスキャン中...")

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )
    if device is None:
        print(f"デバイス '{DEVICE_NAME}' が見つかりませんでした．")
        return

    print(f"接続: {device.name} ({device.address})")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    beta_str = f"{beta:.4f}".rstrip("0").rstrip(".")
    csv_path = DATA_DIR / f"beta{beta_str}_{time.strftime('%Y%m%d_%H%M%S')}.csv"

    madgwick = MadgwickFilter(beta=beta, sample_rate=SAMPLE_RATE)

    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)

        async with BleakClient(device) as client:
            print(f"Ctrl+C で終了. 保存先: {csv_path}")
            await client.start_notify(CHARACTERISTIC_UUID, make_handler(writer, madgwick))
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n終了処理中...")
            finally:
                await client.stop_notify(CHARACTERISTIC_UUID)

    print(f"CSVを保存しました: {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Madgwick β値評価ロガー")
    parser.add_argument("--beta", type=float, default=0.1,
                        help="Madgwickフィルタのβ値（デフォルト: 0.1）")
    args = parser.parse_args()
    asyncio.run(main(args.beta))

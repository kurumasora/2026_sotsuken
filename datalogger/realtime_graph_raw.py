"""
加速度・ジャイロの生データをリアルタイムグラフ表示する.

表示内容:
  - 加速度 [g]
  - 角速度 [deg/s]

使い方:
    cd datalogger
    python realtime_graph_raw.py
"""
from dotenv import load_dotenv
import os
import asyncio
import queue
import struct
import threading

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from bleak import BleakScanner, BleakClient

load_dotenv()

CHARACTERISTIC_UUID = os.getenv('CHARACTERISTIC_UUID')
DEVICE_NAME = os.getenv('DEVICE_NAME')

WINDOW = 200

_queue: queue.Queue = queue.Queue()

_bufs: dict[str, list[float]] = {
    "ax": [], "ay": [], "az": [],
    "gx": [], "gy": [], "gz": [],
}


# ── BLE受信 ──────────────────────────────────────────────

def _ble_handler(sender, data: bytearray) -> None:
    if len(data) == 24:
        _queue.put_nowait(struct.unpack("<ffffff", data))


async def _ble_run() -> None:
    print(f"'{DEVICE_NAME}' をスキャン中...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.local_name == DEVICE_NAME
    )
    if device is None:
        print(f"'{DEVICE_NAME}' が見つかりませんでした.")
        return

    print(f"接続: {device.name} ({device.address})")
    async with BleakClient(device) as client:
        await client.start_notify(CHARACTERISTIC_UUID, _ble_handler)
        print("受信中. グラフウィンドウを閉じると終了します.")
        try:
            while True:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            await client.stop_notify(CHARACTERISTIC_UUID)


def _run_ble_thread() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_ble_run())
    except Exception as e:
        print(f"BLEエラー: {e}")
    finally:
        loop.close()


# ── グラフ ───────────────────────────────────────────────

fig, (ax_accel, ax_gyro) = plt.subplots(2, 1, figsize=(10, 6), sharex=False)
fig.suptitle("IMU Realtime Monitor — Raw", fontsize=13)

_colors = {"x": "#e05252", "y": "#52c05a", "z": "#5288e0"}

_lines_a = {
    k: ax_accel.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_accel.set_ylabel("Acceleration [g]")
ax_accel.set_ylim(-2.5, 2.5)
ax_accel.set_title("Acceleration")
ax_accel.legend(loc="upper right")
ax_accel.grid(True, alpha=0.4)

_lines_g = {
    k: ax_gyro.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_gyro.set_ylabel("Angular velocity [deg/s]")
ax_gyro.set_ylim(-300, 300)
ax_gyro.set_title("Gyro")
ax_gyro.legend(loc="upper right")
ax_gyro.grid(True, alpha=0.4)

plt.tight_layout()


def _update(frame: int):
    while True:
        try:
            ax, ay, az, gx, gy, gz = _queue.get_nowait()
            for key, val in zip(
                ("ax", "ay", "az", "gx", "gy", "gz"),
                (ax, ay, az, gx, gy, gz),
            ):
                _bufs[key].append(val)
                if len(_bufs[key]) > WINDOW:
                    _bufs[key].pop(0)
        except queue.Empty:
            break

    xs = list(range(len(_bufs["ax"])))
    x_max = max(WINDOW, len(xs))

    for k in ("x", "y", "z"):
        _lines_a[k].set_data(xs, _bufs[f"a{k}"])
        _lines_g[k].set_data(xs, _bufs[f"g{k}"])

    ax_accel.set_xlim(0, x_max)
    ax_gyro.set_xlim(0, x_max)

    return list(_lines_a.values()) + list(_lines_g.values())


def main() -> None:
    threading.Thread(target=_run_ble_thread, daemon=True).start()
    animation.FuncAnimation(fig, _update, interval=33, blit=True, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()

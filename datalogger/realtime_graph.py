"""
加速度・ジャイロの6軸データをリアルタイムグラフ表示する独立スクリプト.

表示内容:
  - 加速度 [g]
  - 角速度 [deg/s]
  - 位置 [m]   … 加速度を二重積分（重力を含むため静止でも漂う）
  - 回転角 [deg] … 角速度を積分

操作:
  r キー … 位置・回転角の積分値をリセット

使い方:
    cd datalogger
    python realtime_graph.py
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

WINDOW = 200        # グラフに表示するサンプル数
DT = 1.0 / 30.0    # センサのサンプリング間隔 [s]
G_TO_MS2 = 9.80665 # [m/s²/g]

_queue: queue.Queue = queue.Queue()

# ── 生データバッファ ──────────────────────────────────────
_bufs: dict[str, list[float]] = {
    "ax": [], "ay": [], "az": [],
    "gx": [], "gy": [], "gz": [],
}

# ── 積分バッファ ──────────────────────────────────────────
_bufs_pos: dict[str, list[float]] = {"px": [], "py": [], "pz": []}
_bufs_rot: dict[str, list[float]] = {"rx": [], "ry": [], "rz": []}

# 積分状態
_vel   = [0.0, 0.0, 0.0]   # 速度 [m/s]
_pos   = [0.0, 0.0, 0.0]   # 位置 [m]
_angle = [0.0, 0.0, 0.0]   # 回転角 [deg]


def _reset_integration() -> None:
    for i in range(3):
        _vel[i] = _pos[i] = _angle[i] = 0.0
    for buf in (*_bufs_pos.values(), *_bufs_rot.values()):
        buf.clear()


def _integrate(ax, ay, az, gx, gy, gz) -> None:
    # 加速度 → 速度 → 位置（重力込み、静止でも漂うことに注意）
    for i, a in enumerate([ax, ay, az]):
        _vel[i]   += a * G_TO_MS2 * DT
        _pos[i]   += _vel[i] * DT
    # 角速度 → 回転角
    for i, g in enumerate([gx, gy, gz]):
        _angle[i] += g * DT


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
        print("受信中. グラフウィンドウを閉じると終了します. [r] で積分リセット")
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

fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=False)
ax_accel, ax_gyro, ax_pos, ax_rot = axes
fig.suptitle("IMU Realtime Monitor", fontsize=13)

_colors = {"x": "#e05252", "y": "#52c05a", "z": "#5288e0"}

# 加速度
_lines_a = {
    k: ax_accel.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_accel.set_ylabel("Acceleration [g]")
ax_accel.set_ylim(-2.5, 2.5)
ax_accel.set_title("Acceleration (raw)")
ax_accel.legend(loc="upper right")
ax_accel.grid(True, alpha=0.4)

# 角速度
_lines_g = {
    k: ax_gyro.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_gyro.set_ylabel("Angular velocity [deg/s]")
ax_gyro.set_ylim(-300, 300)
ax_gyro.set_title("Gyro (raw)")
ax_gyro.legend(loc="upper right")
ax_gyro.grid(True, alpha=0.4)

# 位置（二重積分）
_lines_p = {
    k: ax_pos.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_pos.set_ylabel("Position [m]")
ax_pos.set_title("Position (double-integrated accel)  ※重力込みのため静止でも漂う")
ax_pos.legend(loc="upper right")
ax_pos.grid(True, alpha=0.4)

# 回転角（積分）
_lines_r = {
    k: ax_rot.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_rot.set_ylabel("Rotation angle [deg]")
ax_rot.set_title("Rotation angle (integrated gyro)")
ax_rot.legend(loc="upper right")
ax_rot.grid(True, alpha=0.4)

plt.tight_layout()


def _update(frame: int):
    # キューを全部消費してバッファと積分を更新
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

            _integrate(ax, ay, az, gx, gy, gz)

            for key, val in zip(("px", "py", "pz"), _pos):
                _bufs_pos[key].append(val)
                if len(_bufs_pos[key]) > WINDOW:
                    _bufs_pos[key].pop(0)

            for key, val in zip(("rx", "ry", "rz"), _angle):
                _bufs_rot[key].append(val)
                if len(_bufs_rot[key]) > WINDOW:
                    _bufs_rot[key].pop(0)

        except queue.Empty:
            break

    xs = list(range(len(_bufs["ax"])))
    x_max = max(WINDOW, len(xs))
    xs_p = list(range(len(_bufs_pos["px"])))

    for k in ("x", "y", "z"):
        _lines_a[k].set_data(xs, _bufs[f"a{k}"])
        _lines_g[k].set_data(xs, _bufs[f"g{k}"])
        _lines_p[k].set_data(xs_p, _bufs_pos[f"p{k}"])
        _lines_r[k].set_data(xs_p, _bufs_rot[f"r{k}"])

    ax_accel.set_xlim(0, x_max)
    ax_gyro.set_xlim(0, x_max)

    # 位置・回転角はデータに合わせてスケールを自動調整
    for ax_sub, bufs in [(ax_pos, _bufs_pos), (ax_rot, _bufs_rot)]:
        if xs_p:
            ax_sub.set_xlim(0, max(WINDOW, len(xs_p)))
            all_vals = [v for buf in bufs.values() for v in buf]
            if all_vals:
                lo, hi = min(all_vals), max(all_vals)
                margin = max(abs(hi - lo) * 0.1, 0.01)
                ax_sub.set_ylim(lo - margin, hi + margin)

    return (list(_lines_a.values()) + list(_lines_g.values()) +
            list(_lines_p.values()) + list(_lines_r.values()))


def _on_key(event) -> None:
    if event.key == 'r':
        _reset_integration()
        print("積分リセット")


def main() -> None:
    ble_thread = threading.Thread(target=_run_ble_thread, daemon=True)
    ble_thread.start()

    fig.canvas.mpl_connect('key_press_event', _on_key)

    ani = animation.FuncAnimation(
        fig, _update, interval=33, blit=False, cache_frame_data=False
    )
    plt.show()


if __name__ == "__main__":
    main()

"""
加速度・角速度の積分結果をリアルタイムグラフ表示する.

表示内容:
  - 位置 [m]    … 加速度を二重積分（重力込みのため静止でも漂う）
  - 回転角 [deg] … 角速度を積分

操作:
  r キー … 積分値（速度・位置・回転角）をリセット

使い方:
    cd datalogger
    python realtime_graph_integration.py
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
DT = 1.0 / 30.0    # センサのサンプリング間隔 [s]
G_TO_MS2 = 9.80665

_queue: queue.Queue = queue.Queue()

_bufs_pos: dict[str, list[float]] = {"px": [], "py": [], "pz": []}
_bufs_rot: dict[str, list[float]] = {"rx": [], "ry": [], "rz": []}

_vel   = [0.0, 0.0, 0.0]
_pos   = [0.0, 0.0, 0.0]
_angle = [0.0, 0.0, 0.0]


def _reset() -> None:
    for i in range(3):
        _vel[i] = _pos[i] = _angle[i] = 0.0
    for buf in (*_bufs_pos.values(), *_bufs_rot.values()):
        buf.clear()


def _integrate(ax, ay, az, gx, gy, gz) -> None:
    for i, a in enumerate([ax, ay, az]):
        _vel[i] += a * G_TO_MS2 * DT
        _pos[i] += _vel[i] * DT
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

fig, (ax_pos, ax_rot) = plt.subplots(2, 1, figsize=(10, 6), sharex=False)
fig.suptitle("IMU Realtime Monitor — Integration", fontsize=13)

_colors = {"x": "#e05252", "y": "#52c05a", "z": "#5288e0"}

_lines_p = {
    k: ax_pos.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_pos.set_ylabel("Position [m]")
ax_pos.set_title("Position  (double-integrated accel  ※重力込みのため静止でも漂う)")
ax_pos.legend(loc="upper right")
ax_pos.grid(True, alpha=0.4)

_lines_r = {
    k: ax_rot.plot([], [], color=_colors[k], label=k.upper(), linewidth=1.2)[0]
    for k in ("x", "y", "z")
}
ax_rot.set_ylabel("Rotation angle [deg]")
ax_rot.set_title("Rotation angle  (integrated gyro)")
ax_rot.legend(loc="upper right")
ax_rot.grid(True, alpha=0.4)

plt.tight_layout()


def _update(frame: int):
    while True:
        try:
            ax, ay, az, gx, gy, gz = _queue.get_nowait()
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

    xs = list(range(len(_bufs_pos["px"])))
    if not xs:
        return list(_lines_p.values()) + list(_lines_r.values())

    x_max = max(WINDOW, len(xs))
    for k in ("x", "y", "z"):
        _lines_p[k].set_data(xs, _bufs_pos[f"p{k}"])
        _lines_r[k].set_data(xs, _bufs_rot[f"r{k}"])

    for ax_sub, bufs in [(ax_pos, _bufs_pos), (ax_rot, _bufs_rot)]:
        ax_sub.set_xlim(0, x_max)
        all_vals = [v for buf in bufs.values() for v in buf]
        if all_vals:
            lo, hi = min(all_vals), max(all_vals)
            margin = max(abs(hi - lo) * 0.1, 0.01)
            ax_sub.set_ylim(lo - margin, hi + margin)

    return list(_lines_p.values()) + list(_lines_r.values())


def _on_key(event) -> None:
    if event.key == 'r':
        _reset()
        print("積分リセット")


def main() -> None:
    threading.Thread(target=_run_ble_thread, daemon=True).start()
    fig.canvas.mpl_connect('key_press_event', _on_key)
    animation.FuncAnimation(fig, _update, interval=33, blit=False, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()

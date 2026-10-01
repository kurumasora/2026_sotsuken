"""
IMU 6軸データのリアルタイムグラフ表示（PyQtGraph版）.

表示内容:
  - 加速度 [g]
  - 角速度 [deg/s]
  - 位置 [m]    … 加速度を二重積分（重力込みのため静止でも漂う）
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
from collections import deque

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from bleak import BleakScanner, BleakClient

load_dotenv()

CHARACTERISTIC_UUID = os.getenv('CHARACTERISTIC_UUID')
DEVICE_NAME         = os.getenv('DEVICE_NAME')

WINDOW   = 200
DT       = 1.0 / 30.0
G_TO_MS2 = 9.80665

_queue: queue.Queue = queue.Queue()

# ── バッファ（deque で高速な先頭削除）──────────────────────
_buf: dict[str, deque] = {k: deque(maxlen=WINDOW) for k in
    ("ax", "ay", "az", "gx", "gy", "gz", "px", "py", "pz", "rx", "ry", "rz")}

# 積分状態
_vel   = [0.0, 0.0, 0.0]
_pos   = [0.0, 0.0, 0.0]
_angle = [0.0, 0.0, 0.0]


def _reset() -> None:
    for i in range(3):
        _vel[i] = _pos[i] = _angle[i] = 0.0
    for k in ("px", "py", "pz", "rx", "ry", "rz"):
        _buf[k].clear()


def _integrate(ax, ay, az, gx, gy, gz) -> None:
    for i, a in enumerate((ax, ay, az)):
        _vel[i] += a * G_TO_MS2 * DT
        _pos[i] += _vel[i] * DT
    for i, g in enumerate((gx, gy, gz)):
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
        print("受信中. ウィンドウを閉じると終了. [r] で積分リセット")
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


# ── PyQtGraph ウィンドウ ──────────────────────────────────

pg.setConfigOptions(antialias=False)  # 高速化のためアンチエイリアス無効

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

win = pg.GraphicsLayoutWidget(title="IMU Realtime Monitor")
win.resize(1000, 800)
win.setWindowTitle("IMU Realtime Monitor")

COLORS = {"x": "#e05252", "y": "#52c05a", "z": "#5288e0"}

def _make_plot(title: str, ylabel: str, ylim: tuple | None = None) -> tuple:
    p = win.addPlot(title=title)
    p.setLabel("left", ylabel)
    p.addLegend(offset=(1, 1))
    p.showGrid(x=True, y=True, alpha=0.3)
    p.setXRange(0, WINDOW, padding=0)
    if ylim:
        p.setYRange(*ylim, padding=0)
    curves = {
        k: p.plot(pen=pg.mkPen(COLORS[k], width=1.5), name=k.upper())
        for k in ("x", "y", "z")
    }
    return p, curves

p_accel, c_accel = _make_plot("Acceleration",  "Accel [g]",      (-2.5, 2.5))
win.nextRow()
p_gyro,  c_gyro  = _make_plot("Gyro",          "AngVel [deg/s]", (-300, 300))
win.nextRow()
p_pos,   c_pos   = _make_plot("Position  (double-integrated accel  ※重力込みのため静止でも漂う)",
                               "Position [m]")
win.nextRow()
p_rot,   c_rot   = _make_plot("Rotation angle  (integrated gyro)", "Angle [deg]")


def _update() -> None:
    while True:
        try:
            ax, ay, az, gx, gy, gz = _queue.get_nowait()
            for k, v in zip(("ax","ay","az","gx","gy","gz"), (ax,ay,az,gx,gy,gz)):
                _buf[k].append(v)
            _integrate(ax, ay, az, gx, gy, gz)
            for k, v in zip(("px","py","pz"), _pos):
                _buf[k].append(v)
            for k, v in zip(("rx","ry","rz"), _angle):
                _buf[k].append(v)
        except queue.Empty:
            break

    xs = list(range(len(_buf["ax"])))
    for k in ("x", "y", "z"):
        c_accel[k].setData(xs, list(_buf[f"a{k}"]))
        c_gyro[k].setData( xs, list(_buf[f"g{k}"]))

    xp = list(range(len(_buf["px"])))
    for k in ("x", "y", "z"):
        c_pos[k].setData(xp, list(_buf[f"p{k}"]))
        c_rot[k].setData(xp, list(_buf[f"r{k}"]))

    # 位置・回転角のY軸を自動調整
    for p, keys in [(p_pos, ("px","py","pz")), (p_rot, ("rx","ry","rz"))]:
        vals = [v for k in keys for v in _buf[k]]
        if vals:
            lo, hi = min(vals), max(vals)
            margin = max(abs(hi - lo) * 0.1, 0.01)
            p.setYRange(lo - margin, hi + margin, padding=0)


def _on_key(event) -> None:
    if event.key() == QtCore.Qt.Key.Key_R:
        _reset()
        print("積分リセット")


timer = QtCore.QTimer()
timer.timeout.connect(_update)
timer.start(33)  # ~30 fps

win.keyPressEvent = _on_key
win.show()


def main() -> None:
    threading.Thread(target=_run_ble_thread, daemon=True).start()
    app.exec()


if __name__ == "__main__":
    main()

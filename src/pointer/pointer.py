"""Madgwickの姿勢角（roll/pitch）を直接画面座標にマッピングする."""

import math

from src.madgwick import MadgwickFilter

# 画面座標にマッピングする角度の最大値 [deg]
# この角度が画面端に対応する
_MAX_ROLL_DEG  = 45.0  # 手首左右回転の最大角
_MAX_PITCH_DEG = 30.0  # 手首上下屈曲の最大角


_EMA_ALPHA = 0.2  # 小さいほど滑らか（0.1〜0.3が目安）


class PointerController:
    def __init__(self, sample_rate: float = 30.0, beta: float = 0.1):
        self._madgwick = MadgwickFilter(beta=beta, sample_rate=sample_rate)
        self._px = 0.0
        self._py = 0.0
        self._roll  = 0.0
        self._pitch = 0.0

    def update(self, ax: float, ay: float, az: float,
               gx: float, gy: float, gz: float) -> tuple[float, float]:
        self._madgwick.update(ax, ay, az, gx, gy, gz)
        q0, q1, q2, q3 = self._madgwick.quaternion

        # 四元数 → roll / pitch [rad]
        roll  = math.atan2(2*(q0*q1 + q2*q3), 1 - 2*(q1*q1 + q2*q2))
        pitch = math.asin(max(-1.0, min(1.0, 2*(q0*q2 - q3*q1))))

        self._roll  = math.degrees(roll)
        self._pitch = math.degrees(pitch)

        # 角度を [-1, +1] に正規化してEMAで平滑化
        raw_px = -self._roll  / _MAX_ROLL_DEG
        raw_py = -self._pitch / _MAX_PITCH_DEG
        self._px = self._px * (1 - _EMA_ALPHA) + raw_px * _EMA_ALPHA
        self._py = self._py * (1 - _EMA_ALPHA) + raw_py * _EMA_ALPHA

        return self._px, self._py

    def reset(self) -> None:
        pass  # 角度直接マッピングのためリセット不要

    @property
    def position(self) -> tuple[float, float]:
        return self._px, self._py

    @property
    def angles(self) -> tuple[float, float]:
        """roll, pitch [deg]"""
        return self._roll, self._pitch

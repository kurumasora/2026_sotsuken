"""Madgwickフィルタ — ジャイロ＋加速度から四元数で姿勢を推定する."""

import math


class MadgwickFilter:
    def __init__(self, beta: float = 0.1, sample_rate: float = 60.0):
        self._beta = beta
        self._dt = 1.0 / sample_rate
        self._q0, self._q1, self._q2, self._q3 = 1.0, 0.0, 0.0, 0.0

    def update(self, ax: float, ay: float, az: float,
               gx: float, gy: float, gz: float) -> None:
        q0, q1, q2, q3 = self._q0, self._q1, self._q2, self._q3
        gx = math.radians(gx); gy = math.radians(gy); gz = math.radians(gz)

        norm = math.sqrt(ax*ax + ay*ay + az*az)
        if norm < 1e-10:
            return
        ax /= norm; ay /= norm; az /= norm

        f1 = 2.0*(q1*q3 - q0*q2) - ax
        f2 = 2.0*(q0*q1 + q2*q3) - ay
        f3 = 2.0*(0.5 - q1*q1 - q2*q2) - az

        j11=-2.0*q2; j12= 2.0*q3; j13=-2.0*q0; j14= 2.0*q1
        j21= 2.0*q1; j22= 2.0*q0; j23= 2.0*q3; j24= 2.0*q2
        j31= 0.0;    j32=-4.0*q1; j33=-4.0*q2; j34= 0.0

        g0=j11*f1+j21*f2+j31*f3; g1=j12*f1+j22*f2+j32*f3
        g2=j13*f1+j23*f2+j33*f3; g3=j14*f1+j24*f2+j34*f3

        gn = math.sqrt(g0**2+g1**2+g2**2+g3**2)
        if gn > 1e-10:
            g0/=gn; g1/=gn; g2/=gn; g3/=gn

        q0+=(0.5*(-q1*gx-q2*gy-q3*gz)-self._beta*g0)*self._dt
        q1+=(0.5*( q0*gx+q2*gz-q3*gy)-self._beta*g1)*self._dt
        q2+=(0.5*( q0*gy-q1*gz+q3*gx)-self._beta*g2)*self._dt
        q3+=(0.5*( q0*gz+q1*gy-q2*gx)-self._beta*g3)*self._dt

        qn = math.sqrt(q0**2+q1**2+q2**2+q3**2)
        self._q0=q0/qn; self._q1=q1/qn; self._q2=q2/qn; self._q3=q3/qn

    @property
    def quaternion(self) -> tuple[float, float, float, float]:
        return self._q0, self._q1, self._q2, self._q3

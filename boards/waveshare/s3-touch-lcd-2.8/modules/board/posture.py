"""
Posture: 姿态封装，把 QMI8658 的原始读数转换到"开发板坐标系"。
"""

import math

__all__ = ("Posture",)


class Posture:
    """
    姿态封装类。

    用法:
        p = Posture(imu)
        p.update()                          # 刷新缓存
        ax, ay, az = p.get_accel()          # 开发板坐标系 (g)
        gx, gy, gz = p.get_gyro()           # 开发板坐标系 (dps)
        pitch, roll = p.get_pitch_roll()    # 弧度
    """

    __slots__ = (
        "imu",
        "mag",
        "_ax",
        "_ay",
        "_az",
        "_gx",
        "_gy",
        "_gz",
        "_mx",
        "_my",
        "_mz",
        "_temp",
    )

    def __init__(self, imu):
        if imu is None:
            raise ValueError("imu must not be None")
        self.imu = imu

        # 缓存，开发板坐标系
        self._ax = 0.0
        self._ay = 0.0
        self._az = 0.0
        self._gx = 0.0
        self._gy = 0.0
        self._gz = 0.0
        self._mx = 0.0
        self._my = 0.0
        self._mz = 0.0
        self._temp = 0.0
        self.update()

    def update(self):
        """
        从 IMU 读一次原始数据并转换到开发板坐标系，更新缓存。
        返回 True 成功，False 失败（读取异常）。
        """
        try:
            acc, gyr, temp = self.imu.read()
        except Exception:
            return False

        ax_c, ay_c, az_c = acc
        gx_c, gy_c, gz_c = gyr

        # 芯片 → 开发板
        self._ax = +ay_c
        self._ay = -ax_c
        self._az = -az_c

        self._gx = +gy_c
        self._gy = -gx_c
        self._gz = -gz_c

        self._temp = temp
        return True

    # ---------------- 加速度（g） ----------------
    def get_accel(self):
        """返回开发板坐标系下的加速度 (ax, ay, az)，单位 g。"""
        return self._ax, self._ay, self._az

    # ---------------- 角速度（dps） ----------------
    def get_gyro(self):
        """返回开发板坐标系下的角速度 (gx, gy, gz)，单位 dps。"""
        return self._gx, self._gy, self._gz

    # ---------------- 温度 ----------------
    def get_temp(self):
        """返回温度（摄氏度）。"""
        return self._temp

    # ---------------- 姿态角 ----------------
    def get_pitch_roll(self):
        """
        返回 (pitch, roll)，单位弧度。
        约定: 板子水平、屏幕朝上时 (ax, ay, az) ≈ (0, 0, +1)。
        """
        ax, ay, az = self._ax, self._ay, self._az
        pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
        roll = math.atan2(ay, az)
        return pitch, roll

    def get_pitch_roll_deg(self):
        """同 get_pitch_roll，返回角度制。"""
        p, r = self.get_pitch_roll()
        return math.degrees(p), math.degrees(r)

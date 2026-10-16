# Pure Python LVGL indev driver for the Hynitron CST8xx family
#   (CST816S / CST816T / CST816D / CST820 / CST826 / CST836)
#
#       from cst8xx import Cst8xx
#
#       touch = Cst8xx(sda=<pin>, scl=<pin>, width=240, height=240)
#
# 芯片自动识别：读取 0xA7 寄存器获取芯片 ID。
#   CST826/CST836 的 0xA7 返回 0x00，此时改读 0xAA 寄存器。
#
# 寄存器布局（所有型号共用）：
#   0x01: 手势 ID
#   0x02: 手指数量
#   0x03: X_H   0x04: X_L
#   0x05: Y_H   0x06: Y_L
#   0x07: 压力值
#
# 坐标解析：
#   X = ((X_H & 0x0F) << 8) | X_L
#   Y = ((Y_H & 0x0F) << 8) | Y_L
#
# 如果设置了 width/height，超出范围的坐标会被静默拒绝，
# 用于过滤偶发的读取错误。
# 轴交换与反转语义与 FT6X36/CST328 驱动保持一致。

import time

import lvgl as lv
from machine import I2C, Pin

# ---------- 寄存器常量 ----------
CST8XX_REG_GESTURE_ID = 0x01
CST8XX_REG_FINGER_NUM = 0x02
CST8XX_REG_TOUCH_DATA = 0x03  # X_H 起始地址
CST8XX_REG_CHIP_ID = 0xA7
CST8XX_REG_FACTORY_ID = 0xAA  # CST826/CST836 芯片 ID
CST8XX_REG_FW_VERSION = 0xA9

# ---------- 芯片 ID 常量 ----------
CHIP_ID_CST716 = 0x20
CHIP_ID_CST816S = 0xB4
CHIP_ID_CST816T = 0xB5
CHIP_ID_CST816D = 0xB6
CHIP_ID_CST820 = 0xB7
CHIP_ID_CST826 = 0x11
CHIP_ID_CST836 = 0x13

CHIP_NAMES = {
    CHIP_ID_CST716: "CST716",
    CHIP_ID_CST816S: "CST816S",
    CHIP_ID_CST816T: "CST816T",
    CHIP_ID_CST816D: "CST816D",
    CHIP_ID_CST820: "CST820",
    CHIP_ID_CST826: "CST826",
    CHIP_ID_CST836: "CST836",
}

# 支持多点的芯片最大触点数
MULTI_TOUCH_CHIPS = (CHIP_ID_CST826, CHIP_ID_CST836)

# 默认 I2C 地址
CST8XX_DEFAULT_ADDR = 0x15

# ---------- 手势常量 ----------
GESTURE_NONE = 0x00
GESTURE_SWIPE_UP = 0x01
GESTURE_SWIPE_DOWN = 0x02
GESTURE_SWIPE_LEFT = 0x03
GESTURE_SWIPE_RIGHT = 0x04
GESTURE_SINGLE_CLICK = 0x05
GESTURE_DOUBLE_CLICK = 0x0B
GESTURE_LONG_PRESS = 0x0C


class Cst8xx:
    def __init__(
        self,
        i2c_dev=0,
        sda=21,
        scl=22,
        freq=400000,
        addr=CST8XX_DEFAULT_ADDR,
        width=-1,
        height=-1,
        inv_x=False,
        inv_y=False,
        swap_xy=False,
        rst_pin=None,
        irq_pin=None,
    ):

        if not lv.is_initialized():
            lv.init()

        self.width, self.height = width, height
        self.inv_x, self.inv_y, self.swap_xy = inv_x, inv_y, swap_xy
        self.i2c = I2C(i2c_dev, sda=Pin(sda), scl=Pin(scl), freq=freq)
        self.addr = addr

        # 可选硬件复位
        self.rst = None
        if rst_pin is not None:
            self.rst = Pin(rst_pin, Pin.OUT)
            self.rst.value(1)
            time.sleep_ms(10)
            self.rst.value(0)
            time.sleep_ms(10)
            self.rst.value(1)
            time.sleep_ms(50)

        # 自动识别芯片
        self.chip_id = self._detect_chip_id()
        self.chip_name = CHIP_NAMES.get(
            self.chip_id, "Unknown(0x{:02X})".format(self.chip_id)
        )
        self.max_points = 5 if self.chip_id in MULTI_TOUCH_CHIPS else 2

        if self.chip_id == 0x00:
            print("CST8xx touch IC not responding (chip ID 0x00)")
            return
        print(
            "CST8xx touch IC ready: {} (chip ID 0x{:02X})".format(
                self.chip_name, self.chip_id
            )
        )

        # 初始化 LVGL 触点
        self.points = [lv.point_t({"x": 0, "y": 0}) for _ in range(self.max_points)]
        self.state = lv.INDEV_STATE.RELEASED
        self.gesture = GESTURE_NONE
        self.presses = 0

        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)

    def _detect_chip_id(self):
        """自动识别芯片 ID。CST826/CST836 需从 0xAA 读取。"""
        try:
            chip_id = self.i2c.readfrom_mem(self.addr, CST8XX_REG_CHIP_ID, 1)[0]
        except Exception:
            return 0x00

        # CST826/CST836 的 0xA7 返回 0x00，改读 0xAA
        if chip_id == 0x00:
            try:
                chip_id = self.i2c.readfrom_mem(self.addr, CST8XX_REG_FACTORY_ID, 1)[0]
            except Exception:
                pass

        return chip_id

    def callback(self, driver, data):

        def get_point(offset):
            """解析单个触点坐标。offset 指向 X_H 字节（寄存器 0x03）。"""
            x = ((sensorbytes[offset] & 0x0F) << 8) | sensorbytes[offset + 1]
            y = ((sensorbytes[offset + 2] & 0x0F) << 8) | sensorbytes[offset + 3]

            if (self.width != -1 and x >= self.width) or (
                self.height != -1 and y >= self.height
            ):
                raise ValueError

            x = self.width - x - 1 if self.inv_x else x
            y = self.height - y - 1 if self.inv_y else y
            (x, y) = (y, x) if self.swap_xy else (x, y)
            return {"x": x, "y": y}

        data.point = self.points[0]
        data.state = self.state

        try:
            # 读取 手势 + 手指数 + 坐标 + 压力：0x01 ~ 0x07，共 7 字节
            sensorbytes = self.i2c.readfrom_mem(self.addr, CST8XX_REG_GESTURE_ID, 7)
        except Exception:
            return

        self.gesture = sensorbytes[0]
        self.presses = sensorbytes[1] & 0x0F  # 低 4 位为手指数

        if self.presses > self.max_points:
            return

        if self.presses:
            try:
                self.points[0] = get_point(2)  # 坐标从偏移 2（寄存器 0x03）开始
            except ValueError:
                return

        data.point = self.points[0]
        data.state = self.state = (
            lv.INDEV_STATE.PRESSED if self.presses else lv.INDEV_STATE.RELEASED
        )

    def read_gesture(self):
        """手动读取当前手势（供外部查询）。"""
        try:
            return self.i2c.readfrom_mem(self.addr, CST8XX_REG_GESTURE_ID, 1)[0]
        except Exception:
            return GESTURE_NONE

    def deinit(self):
        """释放 LVGL indev 驱动资源。"""
        if hasattr(self, "indev_drv") and self.indev_drv:
            self.indev_drv.delete()
            self.indev_drv = None

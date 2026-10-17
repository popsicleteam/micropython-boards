# Pure Python LVGL indev driver for the Hynitron CST3xx family
#   (CST326 / CST328 / CST340 / CST348 / CST356)
#
#       from cst3xx import Cst3xx
#
#       touch = Cst3xx(i2c_dev=1, sda=1, scl=3, rst_pin=2,
#                      width=240, height=320)
#
# CST3xx 系列使用 16 位寄存器地址，触点数据从 0xD000 开始，共 27 字节。
#
# 数据格式（根据实测原始字节确定）：
#   偏移 0：触摸状态  (0x06 = 按下, 0x00 = 松开)
#   偏移 1：触点 1 的 X 高 8 位
#   偏移 2：触点 1 的 Y 高 8 位
#   偏移 3：X 低 4 位（高半字节） | Y 低 4 位（低半字节）
#   偏移 4：压力值
#   偏移 5：保留
#   ……后续触点每个占 5 字节……
#
# 坐标解析：
#   X = (X_H << 4) | (XY_L >> 4)
#   Y = (Y_H << 4) | (XY_L & 0x0F)
#
# 如果设置了 width/height，超出范围的坐标会被静默拒绝。
# 轴交换与反转语义与 FT6X36/CST8xx 驱动保持一致：
# width/height 和 inv_x/inv_y 均指交换前的坐标系。

import time

import lvgl as lv
from machine import I2C, Pin

# ---------- CST3xx 寄存器常量（16 位地址） ----------
CST3XX_REG_TOUCH_INFO = 0xD000
CST3XX_REG_CHIP_ID = 0xD200
CST3XX_REG_FW_VERSION = 0xD204
CST3XX_REG_MODE_DEBUG = 0xD101
CST3XX_REG_MODE_NORMAL = 0xD109

CST3XX_MAX_POINTS = 5
CST3XX_POINT_SIZE = 5
CST3XX_DATA_SIZE = CST3XX_MAX_POINTS * CST3XX_POINT_SIZE + 2  # 27

CST3XX_DEFAULT_ADDR = 0x1A

# 触摸状态字节的取值
CST3XX_TOUCH_DOWN = 0x06
CST3XX_TOUCH_UP = 0x00


class Cst3xx:
    def __init__(
        self,
        i2c_dev=0,
        sda=21,
        scl=22,
        freq=400000,
        addr=CST3XX_DEFAULT_ADDR,
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

        # 硬件复位
        self.rst = None
        if rst_pin is not None:
            self.rst = Pin(rst_pin, Pin.OUT)
            self.rst.value(1)
            time.sleep_ms(20)
            self.rst.value(0)
            time.sleep_ms(20)
            self.rst.value(1)
            time.sleep_ms(200)  # datasheet 要求复位后等待约 200ms

        # 读取芯片信息（进入 DEBUG_INFO 模式）
        self.chip_id = 0
        self.project_id = 0
        self.fw_major = self.fw_minor = self.fw_build = 0
        if not self._read_chip_info():
            print("CST3xx touch IC not responding or chip info unreadable")
            return
        print(
            "CST3xx touch IC ready (chip type 0x{0:02X}, project 0x{1:02X}, "
            "fw {2:d}.{3:d}.{4:d})".format(
                self.chip_id,
                self.project_id,
                self.fw_major,
                self.fw_minor,
                self.fw_build,
            )
        )

        # LVGL 触点缓冲
        self.points = [lv.point_t({"x": 0, "y": 0}) for _ in range(CST3XX_MAX_POINTS)]
        self.state = lv.INDEV_STATE.RELEASED
        self.presses = 0

        # 注册 LVGL 输入设备
        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)

    # ---------------------------------------------------------
    # 读取芯片信息
    # ---------------------------------------------------------
    def _read_chip_info(self):
        try:
            # 进入 DEBUG_INFO 模式
            self.i2c.writeto_mem(self.addr, CST3XX_REG_MODE_DEBUG, b"", addrsize=16)
            time.sleep_ms(10)

            # 芯片类型 + 项目 ID（0xD200，4 字节）
            buf = self.i2c.readfrom_mem(self.addr, CST3XX_REG_CHIP_ID, 4, addrsize=16)
            self.chip_id = buf[2]  # BYTE2: IC_TYPE
            self.project_id = buf[3]  # BYTE1: PROJECT_ID

            # 固件版本（0xD204，4 字节）
            fw = self.i2c.readfrom_mem(self.addr, CST3XX_REG_FW_VERSION, 4, addrsize=16)
            self.fw_major = fw[0]
            self.fw_minor = fw[1]
            self.fw_build = int.from_bytes(fw[2:4], "big")

            # 切回正常模式
            self.i2c.writeto_mem(self.addr, CST3XX_REG_MODE_NORMAL, b"", addrsize=16)
            time.sleep_ms(10)
            return True
        except Exception as e:
            print("CST3xx chip info read failed:", e)
            try:
                self.i2c.writeto_mem(
                    self.addr, CST3XX_REG_MODE_NORMAL, b"", addrsize=16
                )
            except Exception:
                pass
            return False

    # ---------------------------------------------------------
    # LVGL 读取回调
    # ---------------------------------------------------------
    def callback(self, driver, data):

        def get_point(offset):
            """解析单个触点。offset 指向 X_H（寄存器 0xD001）。
            格式：X_H, Y_H, XY_L, pressure, reserved
            X = (X_H << 4) | (XY_L >> 4)
            Y = (Y_H << 4) | (XY_L & 0x0F)
            """
            x = (sensorbytes[offset] << 4) | (sensorbytes[offset + 2] >> 4)
            y = (sensorbytes[offset + 1] << 4) | (sensorbytes[offset + 2] & 0x0F)

            # 范围过滤
            if (self.width != -1 and x >= self.width) or (
                self.height != -1 and y >= self.height
            ):
                raise ValueError

            # 轴反转 / 交换
            x = self.width - x - 1 if self.inv_x else x
            y = self.height - y - 1 if self.inv_y else y
            (x, y) = (y, x) if self.swap_xy else (x, y)
            return {"x": x, "y": y}

        data.point = self.points[0]
        data.state = self.state

        try:
            sensorbytes = self.i2c.readfrom_mem(
                self.addr, CST3XX_REG_TOUCH_INFO, CST3XX_DATA_SIZE, addrsize=16
            )
        except Exception:
            return

        # ---------- 关键：触摸状态由第 1 个字节决定 ----------
        # 实测：0x06 = 按下，0x00 = 松开
        self.presses = 1 if sensorbytes[0] == CST3XX_TOUCH_DOWN else 0

        if self.presses:
            try:
                self.points[0] = get_point(1)  # 坐标从偏移 1 开始
            except ValueError:
                # 坐标超范围视为无效触摸
                self.presses = 0

        data.point = self.points[0]
        data.state = self.state = (
            lv.INDEV_STATE.PRESSED if self.presses else lv.INDEV_STATE.RELEASED
        )

    # ---------------------------------------------------------
    # 资源释放
    # ---------------------------------------------------------
    def deinit(self):
        if hasattr(self, "indev_drv") and self.indev_drv:
            self.indev_drv.delete()
            self.indev_drv = None

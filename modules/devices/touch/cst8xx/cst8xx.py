# cst8xx.py —— 纯 MicroPython 驱动
import time

from machine import Pin

CST8XX_REG_GESTURE_ID = 0x01
CST8XX_REG_FINGER_NUM = 0x02
CST8XX_REG_TOUCH_DATA = 0x03
CST8XX_REG_CHIP_ID = 0xA7
CST8XX_REG_FACTORY_ID = 0xAA
CST8XX_REG_FW_VERSION = 0xA9

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
MULTI_TOUCH_CHIPS = (CHIP_ID_CST826, CHIP_ID_CST836)
CST8XX_DEFAULT_ADDR = 0x15

GESTURE_NONE = 0x00
GESTURE_SWIPE_UP = 0x01
GESTURE_SWIPE_DOWN = 0x02
GESTURE_SWIPE_LEFT = 0x03
GESTURE_SWIPE_RIGHT = 0x04
GESTURE_SINGLE_CLICK = 0x05
GESTURE_DOUBLE_CLICK = 0x0B
GESTURE_LONG_PRESS = 0x0C


class CST8XX:
    def __init__(
        self,
        i2c_bus,
        addr=CST8XX_DEFAULT_ADDR,
        width=-1,
        height=-1,
        inv_x=False,
        inv_y=False,
        swap_xy=False,
        rst_pin=None,
        irq_pin=None,
    ):
        self.i2c = i2c_bus
        self.addr = addr
        self.width, self.height = width, height
        self.inv_x, self.inv_y, self.swap_xy = inv_x, inv_y, swap_xy

        self.rst = None
        if rst_pin is not None:
            self.rst = Pin(rst_pin, Pin.OUT) if isinstance(rst_pin, int) else rst_pin
            self.rst.value(1)
            time.sleep_ms(10)
            self.rst.value(0)
            time.sleep_ms(10)
            self.rst.value(1)
            time.sleep_ms(50)

        self.chip_id = self._detect_chip_id()
        self.chip_name = CHIP_NAMES.get(
            self.chip_id, "Unknown(0x{:02X})".format(self.chip_id)
        )
        self.max_points = 5 if self.chip_id in MULTI_TOUCH_CHIPS else 2
        self.gesture = GESTURE_NONE
        self.presses = 0
        self.points = [{"x": 0, "y": 0} for _ in range(self.max_points)]

        if self.chip_id == 0x00:
            print("CST8XX touch IC not responding (chip ID 0x00)")
        else:
            print(
                "CST8XX touch IC ready: {} (chip ID 0x{:02X})".format(
                    self.chip_name, self.chip_id
                )
            )

    def _detect_chip_id(self):
        try:
            cid = self.i2c.readfrom_mem(self.addr, CST8XX_REG_CHIP_ID, 1)[0]
        except Exception:
            return 0x00
        if cid == 0x00:
            try:
                cid = self.i2c.readfrom_mem(self.addr, CST8XX_REG_FACTORY_ID, 1)[0]
            except Exception:
                pass
        return cid

    def _parse_point(self, b, o):
        x = ((b[o] & 0x0F) << 8) | b[o + 1]
        y = ((b[o + 2] & 0x0F) << 8) | b[o + 3]
        if (self.width != -1 and x >= self.width) or (
            self.height != -1 and y >= self.height
        ):
            raise ValueError
        x = self.width - x - 1 if self.inv_x else x
        y = self.height - y - 1 if self.inv_y else y
        if self.swap_xy:
            x, y = y, x
        return (x, y)

    def read_touch(self):
        try:
            b = self.i2c.readfrom_mem(self.addr, CST8XX_REG_GESTURE_ID, 7)
        except Exception:
            return None
        self.gesture = b[0]
        presses = b[1] & 0x0F
        if presses > self.max_points or presses == 0:
            self.presses = 0
            return (0, [])
        try:
            pt = self._parse_point(b, 2)
        except ValueError:
            self.presses = 0
            return (0, [])
        self.presses = presses
        self.points[0]["x"], self.points[0]["y"] = pt
        return (presses, [pt])

    def read_gesture(self):
        try:
            return self.i2c.readfrom_mem(self.addr, CST8XX_REG_GESTURE_ID, 1)[0]
        except Exception:
            return GESTURE_NONE

    def deinit(self):
        pass

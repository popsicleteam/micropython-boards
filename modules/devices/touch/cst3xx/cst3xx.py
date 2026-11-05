# cst3xx.py —— 纯 MicroPython 驱动
import time

from machine import Pin

CST3XX_REG_TOUCH_INFO = 0xD000
CST3XX_REG_CHIP_ID = 0xD200
CST3XX_REG_FW_VERSION = 0xD204
CST3XX_REG_MODE_DEBUG = 0xD101
CST3XX_REG_MODE_NORMAL = 0xD109
CST3XX_DATA_SIZE = 5 * 5 + 2
CST3XX_DEFAULT_ADDR = 0x1A
CST3XX_TOUCH_DOWN = 0x06


class CST3XX:
    max_points = 1

    def __init__(
        self,
        i2c_bus,
        addr=CST3XX_DEFAULT_ADDR,
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
            time.sleep_ms(20)
            self.rst.value(0)
            time.sleep_ms(20)
            self.rst.value(1)
            time.sleep_ms(200)

        self.presses = 0
        self.points = [{"x": 0, "y": 0} for _ in range(self.max_points)]

        self.chip_id = self.project_id = 0
        self.fw_major = self.fw_minor = self.fw_build = 0
        self.ok = self._read_chip_info()
        if not self.ok:
            print("CST3XX touch IC not responding or chip info unreadable")
        else:
            print(
                "CST3XX touch IC ready (chip type 0x{0:02X}, project 0x{1:02X}, "
                "fw {2:d}.{3:d}.{4:d})".format(
                    self.chip_id,
                    self.project_id,
                    self.fw_major,
                    self.fw_minor,
                    self.fw_build,
                )
            )

    def _read_chip_info(self):
        try:
            self.i2c.writeto_mem(self.addr, CST3XX_REG_MODE_DEBUG, b"", addrsize=16)
            time.sleep_ms(10)
            b = self.i2c.readfrom_mem(self.addr, CST3XX_REG_CHIP_ID, 4, addrsize=16)
            self.chip_id, self.project_id = b[2], b[3]
            fw = self.i2c.readfrom_mem(self.addr, CST3XX_REG_FW_VERSION, 4, addrsize=16)
            self.fw_major, self.fw_minor = fw[0], fw[1]
            self.fw_build = int.from_bytes(fw[2:4], "big")
            self.i2c.writeto_mem(self.addr, CST3XX_REG_MODE_NORMAL, b"", addrsize=16)
            time.sleep_ms(10)
            return True
        except Exception as e:
            print("CST3XX chip info read failed:", e)
            try:
                self.i2c.writeto_mem(
                    self.addr, CST3XX_REG_MODE_NORMAL, b"", addrsize=16
                )
            except Exception:
                pass
            return False

    def _parse_point(self, buf, o):
        x = (buf[o] << 4) | (buf[o + 2] >> 4)
        y = (buf[o + 1] << 4) | (buf[o + 2] & 0x0F)
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
            buf = self.i2c.readfrom_mem(
                self.addr, CST3XX_REG_TOUCH_INFO, CST3XX_DATA_SIZE, addrsize=16
            )
        except Exception:
            return None

        if buf[0] != CST3XX_TOUCH_DOWN:
            self.presses = 0
            return (0, [])
        try:
            pt = self._parse_point(buf, 1)
        except ValueError:
            self.presses = 0
            return (0, [])

        self.presses = 1
        self.points[0]["x"], self.points[0]["y"] = pt
        return (1, [pt])

    def deinit(self):
        pass

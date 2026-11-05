# xpt2046.py —— 纯 MicroPython 驱动
import struct

import machine

XPT2046_PORTRAIT = const(0)
XPT2046_LANDSCAPE = const(1)
XPT2046_INV_PORTRAIT = const(2)
XPT2046_INV_LANDSCAPE = const(3)


class XPT2046:
    CHAN_X = const(0b0101_0000)
    CHAN_Y = const(0b0001_0000)
    CHAN_Z1 = const(0b0011_0000)
    CHAN_Z2 = const(0b0100_0000)
    CHAN_T0 = const(0b0000_0000)
    CHAN_T1 = const(0b0111_0000)
    CHAN_BAT = const(0b0010_0000)
    CHAN_AUX = const(0b0110_0000)

    CONV_8_BIT = const(0b0000_1000)
    CONV_12_BIT = const(0b0000_0000)
    START_BIT = const(0b1000_0000)

    max_points = 1

    def __init__(
        self,
        spi,
        cs,
        bits=12,
        ranges=((100, 1900), (200, 1950)),
        width=240,
        height=320,
        rot=XPT2046_PORTRAIT,
        spiRate=24_000_000,
        spiPrereadCb=None,
    ):
        self.buf = bytearray(3)
        self.spi = spi
        self.cs = machine.Pin(cs, machine.Pin.OUT) if isinstance(cs, int) else cs
        self.cs.value(1)

        if bits not in (8, 12):
            raise ValueError("XPT2046.bits: must be 8 or 12")
        self.conv = XPT2046.CONV_8_BIT if bits == 8 else XPT2046.CONV_12_BIT
        self.xy_range, self.dim, self.rot = ranges, (width, height), rot % 4
        self.xy_scale = [
            self.dim[ax] * 1.0 / (self.xy_range[ax][1] - self.xy_range[ax][0])
            for ax in (0, 1)
        ]
        self.xy_origin = [self.xy_range[ax][0] for ax in (0, 1)]

        self.spiRate = spiRate
        self.spiPrereadCb = spiPrereadCb

        self.presses = 0
        self.points = [{"x": 0, "y": 0}]

    # ---- 底层通道读取 ----
    def _chan_read(self, chan):
        self.cs.value(0)
        struct.pack_into("BBB", self.buf, 0, XPT2046.START_BIT | self.conv | chan, 0, 0)
        self.spi.write_readinto(self.buf, self.buf)
        if self.conv == XPT2046.CONV_8_BIT:
            ret = self.buf[1]
        else:
            ret = (self.buf[1] << 4) | (self.buf[2] >> 4)
        self.cs.value(1)
        return ret

    # ---- 坐标换算 ----
    def _raw2px(self, rxy):
        x, y = [
            int(self.xy_scale[ax] * (rxy[ax] - self.xy_origin[ax])) for ax in (0, 1)
        ]
        if self.rot == 0:
            return self.dim[0] - x, y
        elif self.rot == 1:
            return self.dim[1] - y, x
        elif self.rot == 2:
            return x, self.dim[1] - y
        else:
            return y, self.dim[0] - x

    def _raw_pos(self):
        ret = [0, 0]
        for ax, chan in ((0, XPT2046.CHAN_X), (1, XPT2046.CHAN_Y)):
            r = self._chan_read(chan)
            if not self.xy_range[ax][0] <= r <= self.xy_range[ax][1]:
                return None
            ret[ax] = r
        return ret

    def pos(self, N=10, attempts=20):
        xx = yy = done = 0
        for _ in range(attempts):
            r = self._raw_pos()
            if r is None:
                continue
            xx += r[0]
            yy += r[1]
            done += 1
            if done == N:
                break
        else:
            return None
        return self._raw2px((xx * 1.0 / N, yy * 1.0 / N))

    # ---- 硬件读接口 ----
    def read_touch(self):
        if self.spiPrereadCb:
            self.spiPrereadCb()
        if self.spiRate:
            self.spi.init(baudrate=1_000_000)
        try:
            pos = self.pos()
        finally:
            if self.spiRate:
                self.spi.init(baudrate=self.spiRate)
        if pos is None:
            self.presses = 0
            return (0, [])
        self.presses = 1
        self.points[0]["x"], self.points[0]["y"] = pos
        return (1, [pos])

    def deinit(self):
        pass

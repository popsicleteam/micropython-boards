# st77xx.py —— 纯 MicroPython 显示驱动

import struct
import time

import machine
import uctypes

from micropython import const

# ---------- 寄存器常量 ----------
ST77XX_NOP = const(0x00)
ST77XX_SWRESET = const(0x01)
ST77XX_RDDID = const(0x04)
ST77XX_RDDST = const(0x09)

ST77XX_SLPIN = const(0x10)
ST77XX_SLPOUT = const(0x11)
ST77XX_PTLON = const(0x12)
ST77XX_NORON = const(0x13)

ST77XX_INVOFF = const(0x20)
ST77XX_INVON = const(0x21)
ST77XX_DISPOFF = const(0x28)
ST77XX_DISPON = const(0x29)

ST77XX_CASET = const(0x2A)
ST77XX_RASET = const(0x2B)
ST77XX_RAMWR = const(0x2C)
ST77XX_RAMRD = const(0x2E)

ST77XX_PTLAR = const(0x30)
ST77XX_MADCTL = const(0x36)
ST77XX_COLMOD = const(0x3A)

ST7789_WRCACE = const(0x55)

ST77XX_FRMCTR1 = const(0xB1)
ST77XX_FRMCTR2 = ST7789_PORCTRL = const(0xB2)
ST77XX_FRMCTR3 = const(0xB3)
ST77XX_INVCTR = const(0xB4)
ST7789_DISSET5 = const(0xB6)

ST7789_GCTRL = const(0xB7)
ST7789_GTADJ = const(0xB8)
ST7789_VCOMS = const(0xBB)

ST7735_PWCTR1 = ST7789_LCMCTRL = const(0xC0)
ST7735_PWCTR2 = ST7789_IDSET = const(0xC1)
ST7735_PWCTR3 = ST7789_VDVVRHEN = const(0xC2)
ST7735_PWCTR4 = ST7789_VRHS = const(0xC3)
ST7735_PWCTR5 = ST7789_VDVS = const(0xC4)
ST7735_VMCTR1 = ST7789_VMCTR1 = const(0xC5)
ST7789_FRCTRL2 = const(0xC6)
ST7789_CABCCTRL = const(0xC7)

ST7789_PWCTRL1 = const(0xD0)
ST77XX_RDID1 = const(0xDA)
ST77XX_RDID2 = const(0xDB)
ST77XX_RDID3 = const(0xDC)
ST77XX_RDID4 = const(0xDD)

ST7789_GMCTRP1 = ST7789_PVGAMCTRL = const(0xE0)
ST7789_GMCTRN1 = ST7789_NVGAMCTRL = const(0xE1)

ST7735_PWCTR6 = ST7789_PWCTR6 = const(0xFC)

# ---------- MADCTL 位 ----------
ST77XX_MADCTL_MY = const(0x80)
ST77XX_MADCTL_MX = const(0x40)
ST77XX_MADCTL_MV = const(0x20)
ST77XX_MADCTL_ML = const(0x10)
ST77XX_MADCTL_BGR = const(0x08)
ST77XX_MADCTL_RTL = const(0x04)
ST77XX_MADCTL_ROTS = (
    const(0x00),
    const(ST77XX_MADCTL_MX | ST77XX_MADCTL_MV),
    const(ST77XX_MADCTL_MY | ST77XX_MADCTL_MX),
    const(ST77XX_MADCTL_MY | ST77XX_MADCTL_MV),
)

# ---------- 颜色模式 ----------
ST77XX_COLOR_MODE_65K = const(0x50)
ST77XX_COLOR_MODE_262K = const(0x60)
ST77XX_COLOR_MODE_12BIT = const(0x03)
ST77XX_COLOR_MODE_16BIT = const(0x05)
ST77XX_COLOR_MODE_18BIT = const(0x06)
ST77XX_COLOR_MODE_16M = const(0x07)

# ---------- 起始偏移映射 ----------
ST77XX_COL_ROW_MODEL_START_ROTMAP = {
    # ST7789
    (240, 320, None): [(0, 0), (0, 0), (0, 0), (0, 0)],
    (170, 320, None): [(35, 0), (0, 35), (35, 0), (0, 35)],
    (240, 280, None): [(0, 20), (20, 0), (0, 20), (20, 0)],
    (240, 240, None): [(0, 0), (0, 0), (0, 80), (80, 0)],
    (135, 240, None): [(52, 40), (40, 53), (53, 40), (40, 52)],
    # ST7735
    (128, 160, "blacktab"): [(0, 0), (0, 0), (0, 0), (0, 0)],
    (128, 160, "redtab"): [(2, 1), (1, 2), (2, 1), (1, 2)],
}

ST77XX_PORTRAIT = const(0)
ST77XX_LANDSCAPE = const(1)
ST77XX_INV_PORTRAIT = const(2)
ST77XX_INV_LANDSCAPE = const(3)


class ST77XX:
    """
    ST77xx 系列硬件驱动基类（抽象，请使用 ST7735 / ST7789）。
    """

    def __init__(
        self,
        *,
        cs,
        dc,
        spi,
        res,
        suppRes,
        bl=None,
        model=None,
        suppModel=[],
        rst=None,
        rot=ST77XX_LANDSCAPE,
        bgr=False,
        inv=False,
        rp2_dma=None,
    ):
        self.buf1 = bytearray(1)
        self.buf2 = bytearray(2)
        self.buf4 = bytearray(4)

        self.cs, self.dc, self.rst = [
            (machine.Pin(p, machine.Pin.OUT) if isinstance(p, int) else p)
            for p in (cs, dc, rst)
        ]
        self.bl = bl
        if hasattr(machine, "PWM"):
            if isinstance(self.bl, int):
                self.bl = machine.PWM(machine.Pin(self.bl, machine.Pin.OUT))
            elif isinstance(self.bl, machine.Pin):
                self.bl = machine.PWM(self.bl)
            assert isinstance(self.bl, (machine.PWM, type(None)))
        self.set_backlight(10)

        self.rot = rot
        self.bgr = bgr
        self.inv = inv
        self.width, self.height = (0, 0)

        if res not in suppRes:
            raise ValueError(
                "Unsupported resolution %s; supported: %s."
                % (str(res), ", ".join(str(r) for r in suppRes))
            )
        if suppModel and model not in suppModel:
            raise ValueError(
                "Unsupported model %s; supported: %s."
                % (str(model), ", ".join(str(r) for r in suppModel))
            )

        self.res = res
        self.model = model

        self.rp2_dma = rp2_dma
        self.spi = spi
        self.hard_reset()

    # ---------- 电源 / 背光 / 反色 ----------
    def off(self):
        self.set_backlight(0)

    def hard_reset(self):
        if self.rst:
            for v in (1, 0, 1):
                self.rst.value(v)
                time.sleep(0.2)
            time.sleep(0.2)
        self.config()

    def config(self):
        self.config_hw()  # 子类实现
        self.set_rotation(self.rot)

    def set_backlight(self, percent):
        if self.bl is None:
            return
        self.bl.duty_u16(percent * 655)

    def set_inversion(self, inv):
        """运行时切换显示反色；可在初始化之后随时调用。"""
        self.inv = inv
        self.write_register(ST77XX_INVON if inv else ST77XX_INVOFF, None)

    # ---------- 窗口 / 旋转 ----------
    def set_window(self, x, y, w, h):
        c0, r0 = ST77XX_COL_ROW_MODEL_START_ROTMAP[
            self.res[0], self.res[1], self.model
        ][self.rot % 4]
        struct.pack_into(">hh", self.buf4, 0, c0 + x, c0 + x + w - 1)
        self.write_register(ST77XX_CASET, self.buf4)
        struct.pack_into(">hh", self.buf4, 0, r0 + y, r0 + y + h - 1)
        self.write_register(ST77XX_RASET, self.buf4)

    def set_rotation(self, rot):
        self.rot = rot
        if (self.rot % 2) == 0:
            self.width, self.height = self.res
        else:
            self.height, self.width = self.res
        self.write_register(
            ST77XX_MADCTL,
            bytes(
                [
                    (ST77XX_MADCTL_BGR if self.bgr else 0)
                    | ST77XX_MADCTL_ROTS[self.rot % 4]
                ]
            ),
        )

    # ---------- 写像素 ----------
    def blit(self, x, y, w, h, buf, is_blocking=True):
        self.set_window(x, y, w, h)
        if self.rp2_dma:
            self._rp2_write_register_dma(ST77XX_RAMWR, buf, is_blocking)
        else:
            self.write_register(ST77XX_RAMWR, buf)

    def clear(self, color):
        bs = 128
        struct.pack_into(">h", self.buf2, 0, color)
        buf = bs * bytes(self.buf2)
        npx = self.width * self.height
        self.set_window(0, 0, self.width, self.height)
        self.write_register(ST77XX_RAMWR, None)
        self.cs.value(0)
        self.dc.value(1)
        for _ in range(npx // bs):
            self.spi.write(buf)
        for _ in range(npx % bs):
            self.spi.write(self.buf2)
        self.cs.value(1)

    def write_register(self, reg, buf=None):
        struct.pack_into("B", self.buf1, 0, reg)
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(self.buf1)
        if buf is not None:
            self.dc.value(1)
            self.spi.write(buf)
        self.cs.value(1)

    # ---------- rp2 DMA ----------
    def _rp2_write_register_dma(self, reg, buf, is_blocking=True):
        SPI1_BASE = 0x40040000
        SSPDR = 0x008
        self.rp2_dma.config(
            src_addr=uctypes.addressof(buf),
            dst_addr=SPI1_BASE + SSPDR,
            count=len(buf),
            src_inc=True,
            dst_inc=False,
            trig_dreq=self.rp2_dma.DREQ_SPI1_TX,
        )
        struct.pack_into("B", self.buf1, 0, reg)
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(self.buf1)
        self.dc.value(1)
        self.rp2_dma.enable()
        if is_blocking:
            self.rp2_wait_dma()

    def rp2_wait_dma(self):
        if self.rp2_dma is None:
            return
        while self.rp2_dma.is_busy():
            pass
        self.rp2_dma.disable()
        time.sleep_us(1)
        self.cs.value(1)

    # ---------- 命令序列 ----------
    def _run_seq(self, seq):
        for i, cmd in enumerate(seq):
            if len(cmd) == 2:
                (reg, data), delay = cmd, 0
            elif len(cmd) == 3:
                reg, data, delay = cmd
            else:
                raise ValueError(
                    "Command #%d has %d items (must be 2 or 3)" % (i, len(cmd))
                )
            self.write_register(reg, data)
            if delay > 0:
                time.sleep_ms(delay)

    def deinit(self):
        pass


class ST7735(ST77XX):
    def __init__(self, res, model="greentab", **kw):
        super().__init__(
            res=res,
            suppRes=[(128, 160)],
            model=model,
            suppModel=["greentab", "redtab", "blacktab"],
            **kw,
        )

    def config_hw(self):
        init7735r = [
            (ST77XX_SWRESET, None, 50),
            (ST77XX_SLPOUT, None, 100),
            (ST77XX_FRMCTR1, b"\x01\x2c\x2d"),
            (ST77XX_FRMCTR2, b"\x01\x2c\x2d"),
            (ST77XX_FRMCTR3, b"\x01\x2c\x2d\x01\x2c\x2d"),
            (ST77XX_INVCTR, b"\x07"),
            (ST7735_PWCTR1, b"\xa2\x02\xb4"),
            (ST7735_PWCTR2, b"\xc5"),
            (ST7735_PWCTR3, b"\x0a\x00"),
            (ST7735_PWCTR4, b"\x8a\x2a"),
            (ST7735_PWCTR5, b"\x8a\xee"),
            (ST7735_VMCTR1, b"\x0e"),
            (ST77XX_INVON if self.inv else ST77XX_INVOFF, None),
            (ST77XX_COLMOD, bytes([ST77XX_COLOR_MODE_65K | ST77XX_COLOR_MODE_16BIT])),
            (ST77XX_CASET, bytes([0x00, 0x00, 0x00, 0x7F])),
            (ST77XX_RASET, bytes([0x00, 0x00, 0x00, 0x9F])),
            (
                ST7789_GMCTRP1,
                b"\x0f\x1a\x0f\x18\x2f\x28\x20\x22\x1f\x1b\x23\x37\x00\x07\x02\x10",
            ),
            (
                ST7789_GMCTRN1,
                b"\x0f\x1b\x0f\x17\x33\x2c\x29\x2e\x30\x30\x39\x3f\x00\x07\x03\x10",
            ),
            (ST77XX_NORON, None, 10),
            (ST77XX_DISPON, None, 100),
        ]
        init7735 = [
            (ST77XX_SWRESET, None, 50),
            (ST77XX_SLPOUT, None, 100),
            (ST77XX_COLMOD, bytes([ST77XX_COLOR_MODE_65K | ST77XX_COLOR_MODE_16BIT])),
            (ST77XX_FRMCTR1, bytes([0x00, 0x06, 0x03])),
            (ST77XX_MADCTL, bytes([0x03])),
            (ST77XX_INVCTR, b"\x00"),
            (ST7735_PWCTR1, b"\x02\x70"),
            (ST7735_PWCTR2, b"\x05"),
            (ST7735_PWCTR3, b"\x01\x02"),
            (ST7735_VMCTR1, b"\x3c\x38"),
            (ST7735_PWCTR6, b"\b11\b15"),
            (ST77XX_INVON if self.inv else ST77XX_INVOFF, None),
            (ST77XX_NORON, None, 10),
            (ST77XX_DISPON, None, 100),
        ]
        if self.model in ("redtab", "blacktab"):
            self._run_seq(init7735r)
        else:
            print("Warning: the greentab model was never properly tested")
            self._run_seq(init7735)


class ST7789(ST77XX):
    def __init__(self, res, **kw):
        super().__init__(
            res=res,
            suppRes=[
                (240, 320),
                (170, 320),
                (240, 280),
                (240, 240),
                (135, 240),
            ],
            model=None,
            suppModel=None,
            **kw,
        )

    def config_hw(self):
        init7789 = [
            (ST77XX_SLPOUT, None, 100),
            (ST77XX_MADCTL, bytes([ST77XX_MADCTL_ROTS[self.rot % 4]])),
            (ST77XX_COLMOD, bytes([ST77XX_COLOR_MODE_65K | ST77XX_COLOR_MODE_16BIT])),
            (ST7789_PORCTRL, b"\x0c\x0c\x00\x33\x33"),
            (ST7789_GCTRL, b"\x35"),
            (ST77XX_DISPOFF, b"\x28"),
            (ST7789_LCMCTRL, b"\x3c"),
            (ST7789_VDVVRHEN, b"\x01"),
            (ST7789_VRHS, b"\x0b"),
            (ST7789_VDVS, b"\x20"),
            (ST7789_FRCTRL2, b"\x0f"),
            (ST7789_PWCTRL1, b"\xa4\xa1"),
            (
                ST7789_PVGAMCTRL,
                b"\xd0\x01\x08\x0f\x11\x2a\x36\x55\x44\x3a\x0b\x06\x11\x20",
            ),
            (
                ST7789_NVGAMCTRL,
                b"\xd0\x02\x07\x0a\x0b\x18\x34\x43\x4a\x2b\x1b\x1c\x22\x1f",
            ),
            (ST7789_WRCACE, bytes([0b1011_0000])),
            # inv 必须早于 DISPON
            (ST77XX_INVON if self.inv else ST77XX_INVOFF, None),
            (ST77XX_DISPON, None, 100),
            (ST77XX_SLPOUT, None, 100),
        ]
        self._run_seq(init7789)

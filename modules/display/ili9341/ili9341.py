# ili9341.py —— 纯 MicroPython 显示驱动

import st77xx

from micropython import const

# ---------- ILI9341 命令常量 ----------
_NOP = const(0x00)
_SWRESET = const(0x01)
_RDDID = const(0x04)
_RDDST = const(0x09)
_SLPIN = const(0x10)
_SLPOUT = const(0x11)
_PTLON = const(0x12)
_NORON = const(0x13)
_RDMODE = const(0x0A)
_RDMADCTL = const(0x0B)
_RDPIXFMT = const(0x0C)
_RDIMGFMT = const(0x0D)
_RDSELFDIAG = const(0x0F)
_INVOFF = const(0x20)
_INVON = const(0x21)
_GAMMASET = const(0x26)
_DISPLAY_OFF = const(0x28)
_DISPLAY_ON = const(0x29)
_SET_COLUMN = const(0x2A)
_SET_PAGE = const(0x2B)
_WRITE_RAM = const(0x2C)
_READ_RAM = const(0x2E)
_PTLAR = const(0x30)
_VSCRDEF = const(0x33)
_MADCTL = const(0x36)
_VSCRSADD = const(0x37)
_PIXFMT = const(0x3A)
_WRITE_DISPLAY_BRIGHTNESS = const(0x51)
_READ_DISPLAY_BRIGHTNESS = const(0x52)
_WRITE_CTRL_DISPLAY = const(0x53)
_READ_CTRL_DISPLAY = const(0x54)
_WRITE_CABC = const(0x55)
_READ_CABC = const(0x56)
_WRITE_CABC_MINIMUM = const(0x5E)
_READ_CABC_MINIMUM = const(0x5F)
_FRMCTR1 = const(0xB1)
_FRMCTR2 = const(0xB2)
_FRMCTR3 = const(0xB3)
_INVCTR = const(0xB4)
_DFUNCTR = const(0xB6)
_PWCTR1 = const(0xC0)
_PWCTR2 = const(0xC1)
_PWCTRA = const(0xCB)
_PWCTRB = const(0xCF)
_VMCTR1 = const(0xC5)
_VMCTR2 = const(0xC7)
_RDID1 = const(0xDA)
_RDID2 = const(0xDB)
_RDID3 = const(0xDC)
_RDID4 = const(0xDD)
_GMCTRP1 = const(0xE0)
_GMCTRN1 = const(0xE1)
_DTCA = const(0xE8)
_DTCB = const(0xEA)
_POSC = const(0xED)
_ENABLE3G = const(0xF2)
_PUMPRC = const(0xF7)

# ---------- MADCTL 位 ----------
_MADCTL_MY = const(0x80)
_MADCTL_MX = const(0x40)
_MADCTL_MV = const(0x20)
_MADCTL_ML = const(0x10)
_MADCTL_BGR = const(0x08)
_MADCTL_RTL = const(0x04)

_MADCTL_ROTS = (
    const(_MADCTL_MX),
    const(_MADCTL_MV),
    const(_MADCTL_MY),
    const(_MADCTL_MX | _MADCTL_MY | _MADCTL_MV),
)

# ---------- 对外旋转常量 ----------
ILI9341_PORTRAIT = st77xx.ST77XX_PORTRAIT
ILI9341_LANDSCAPE = st77xx.ST77XX_LANDSCAPE
ILI9341_INV_PORTRAIT = st77xx.ST77XX_INV_PORTRAIT
ILI9341_INV_LANDSCAPE = st77xx.ST77XX_INV_LANDSCAPE


class ILI9341(st77xx.ST77XX):
    """ILI9341 TFT 显示驱动（纯硬件层，无 LVGL 依赖）。"""

    def __init__(self, **kw):
        super().__init__(
            res=(240, 320),
            suppRes=[(240, 320)],
            model=None,
            suppModel=None,
            bgr=False,
            **kw,
        )

    def config_hw(self):
        self._run_seq(
            [
                (_SLPOUT, None, 100),
                (_PWCTRB, b"\x00\xc1\x30"),
                (_POSC, b"\x64\x03\x12\x81"),
                (_DTCA, b"\x85\x00\x78"),
                (_PWCTRA, b"\x39\x2c\x00\x34\x02"),
                (_PUMPRC, b"\x20"),
                (_DTCB, b"\x00\x00"),
                (_PWCTR1, b"\x23"),
                (_PWCTR2, b"\x10"),
                (_VMCTR1, b"\x3e\x28"),
                (_VMCTR2, b"\x86"),
                (_VSCRSADD, b"\x00"),
                (_PIXFMT, b"\x55"),
                (_FRMCTR1, b"\x00\x18"),
                (_DFUNCTR, b"\x08\x82\x27"),
                (_ENABLE3G, b"\x00"),
                (_GAMMASET, b"\x01"),
                (
                    _GMCTRP1,
                    b"\x0f\x31\x2b\x0c\x0e\x08\x4e\xf1\x37\x07\x10\x03\x0e\x09\x00",
                ),
                (
                    _GMCTRN1,
                    b"\x00\x0e\x14\x03\x11\x07\x31\xc1\x48\x08\x0f\x0c\x31\x36\x0f",
                ),
                (_INVON if self.inv else _INVOFF, None),
                (_SLPOUT, None, 100),
                (_DISPLAY_ON, None),
            ]
        )

    def set_rotation(self, rot):
        self.rot = rot
        if (self.rot % 2) == 0:
            self.width, self.height = self.res
        else:
            self.height, self.width = self.res
        self.write_register(
            _MADCTL,
            bytes([_MADCTL_BGR | _MADCTL_ROTS[self.rot % 4]]),
        )

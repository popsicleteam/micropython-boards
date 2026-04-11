import ili9341
from ili9341 import Ili9341_hw
from st77xx import St77xx_lvgl


class ILI9341(Ili9341_hw, St77xx_lvgl):
    PORTRAIT = ili9341.ILI9XXX_PORTRAIT
    LANDSCAPE = ili9341.ILI9XXX_LANDSCAPE
    INV_PORTRAIT = ili9341.ILI9XXX_INV_PORTRAIT
    INV_LANDSCAPE = ili9341.ILI9XXX_INV_LANDSCAPE

    def __init__(self, res, doublebuffer=True, factor=4, **kw):
        Ili9341_hw.__init__(self, res=res, **kw)
        St77xx_lvgl.__init__(self, doublebuffer, factor)

import st77xx
from st77xx import St77xx_lvgl, St7735_hw


class ST7735(St7735_hw, St77xx_lvgl):
    PORTRAIT = st77xx.ST77XX_PORTRAIT
    LANDSCAPE = st77xx.ST77XX_LANDSCAPE
    INV_PORTRAIT = st77xx.ST77XX_INV_PORTRAIT
    INV_LANDSCAPE = st77xx.ST77XX_INV_LANDSCAPE

    def __init__(self, res, doublebuffer=True, factor=4, **kw):
        St7735_hw.__init__(self, res=res, **kw)
        St77xx_lvgl.__init__(self, doublebuffer, factor)

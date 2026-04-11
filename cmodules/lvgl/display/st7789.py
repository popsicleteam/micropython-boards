import st77xx
from st77xx import St77xx_hw, St77xx_lvgl, St7789_hw

# fixed
st77xx.ST77XX_COL_ROW_MODEL_START_ROTMAP = {
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


class ST7789(St7789_hw, St77xx_lvgl):
    PORTRAIT = st77xx.ST77XX_PORTRAIT
    LANDSCAPE = st77xx.ST77XX_LANDSCAPE
    INV_PORTRAIT = st77xx.ST77XX_INV_PORTRAIT
    INV_LANDSCAPE = st77xx.ST77XX_INV_LANDSCAPE

    def __init__(self, res, doublebuffer=True, factor=4, **kw):
        St77xx_hw.__init__(
            self,
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
        St77xx_lvgl.__init__(self, doublebuffer, factor)

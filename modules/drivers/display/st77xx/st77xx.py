import _st77xx
from _st77xx import (
    ST77XX_INV_LANDSCAPE,
    ST77XX_INV_PORTRAIT,
    ST77XX_INVOFF,
    ST77XX_INVON,
    ST77XX_LANDSCAPE,
    ST77XX_PORTRAIT,
    St77xx_hw,
    St77xx_lvgl,
    St7789_hw,
)

# Fixed
_st77xx.ST77XX_COL_ROW_MODEL_START_ROTMAP = {
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


class St7789(St7789_hw, St77xx_lvgl):
    def __init__(self, res, doublebuffer=True, factor=4, inv=False, **kw):
        self.inv = inv
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

    def config_hw(self):
        super().config_hw()
        if self.inv:
            self.write_register(ST77XX_INVON, None)
        else:
            self.write_register(ST77XX_INVOFF, None)

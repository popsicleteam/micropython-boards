# lv_touch.py
#
# 为实现了 read_touch() 的触摸驱动注册 LVGL 指针输入设备。
#
# 驱动契约（无需 import lvgl）：
#   touch.max_points     -> int（可选，默认 1）
#   touch.read_touch()   -> (presses, [(x, y), ...]) 或 None
#   touch.presses        -> 最近一次读数
#   touch.points         -> [{'x':..,'y':..}, ...]
#
# 用法：
#   from lv_touch import lv_touch_register
#   lv_touch = lv_touch_register(touch)
#   ...
#   lv_touch.deinit()

import lvgl as lv


def lv_touch_register(touch, max_points=None):
    """为触摸驱动创建并注册 LVGL 指针输入设备。"""
    if not touch:
        return
    if not lv.is_initialized():
        lv.init()
    if max_points is None:
        max_points = getattr(touch, "max_points", 1)
    return LvglTouch(touch, max_points)


class LvglTouch:
    def __init__(self, touch, max_points=1):
        self.touch = touch
        self.max_points = max_points
        self.points = [lv.point_t({"x": 0, "y": 0}) for _ in range(max_points)]
        self.state = lv.INDEV_STATE.RELEASED
        self.presses = 0

        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self._callback)

    def _callback(self, driver, data):
        data.point = self.points[0]
        data.state = self.state
        try:
            result = self.touch.read_touch()
        except Exception:
            result = None

        if result is None:
            self.presses = 0
        else:
            presses, coords = result
            if presses > self.max_points:
                presses = self.max_points
            self.presses = presses
            for i in range(presses):
                x, y = coords[i]
                self.points[i].x = x
                self.points[i].y = y

        data.point = self.points[0]
        data.state = self.state = (
            lv.INDEV_STATE.PRESSED if self.presses else lv.INDEV_STATE.RELEASED
        )

    def deinit(self):
        if self.indev_drv:
            self.indev_drv.delete()
            self.indev_drv = None

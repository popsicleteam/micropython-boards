# lv_display.py
#
# 为实现了 blit() 的显示驱动注册 LVGL 显示设备。
#
# 驱动契约（无需 import lvgl）：
#   disp.width / disp.height   -> 当前旋转方向下的分辨率
#   disp.bgr                   -> bool，True 时 RGB565 交换字节顺序
#   disp.blit(x, y, w, h, buf, is_blocking=True)
#   disp.rp2_wait_dma()        -> 可选：等待 DMA 完成
#
# 用法：
#   from lv_display import lv_display_register
#   lv_disp = lv_display_register(disp, doublebuffer=True, factor=4)
#   ...
#   lv_disp.deinit()

import lv_utils
import lvgl as lv


def lv_display_register(disp, doublebuffer=True, factor=4):
    """为显示驱动创建并注册 LVGL 显示设备。"""
    if not disp:
        return
    if not lv.is_initialized():
        lv.init()
    return LvglDisplay(disp, doublebuffer=doublebuffer, factor=factor)


class LvglDisplay:
    def __init__(self, disp, doublebuffer=True, factor=4):
        self.disp = disp

        if not lv_utils.event_loop.is_running():
            self.event_loop = lv_utils.event_loop()

        color_format = lv.COLOR_FORMAT.RGB565
        self.pixel_size = lv.color_format_get_size(color_format)
        self.rgb565_swap_func = None if disp.bgr else lv.draw_sw_rgb565_swap

        draw_buf1 = lv.draw_buf_create(
            disp.width, disp.height // factor, color_format, 0
        )
        draw_buf2 = (
            lv.draw_buf_create(disp.width, disp.height // factor, color_format, 0)
            if doublebuffer
            else None
        )

        self.disp_drv = lv.display_create(disp.width, disp.height)
        self.disp_drv.set_color_format(color_format)
        self.disp_drv.set_draw_buffers(draw_buf1, draw_buf2)
        self.disp_drv.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
        self.disp_drv.set_flush_cb(self._flush_cb)

    def _flush_cb(self, disp_drv, area, color_p):
        disp = self.disp

        wait = getattr(disp, "rp2_wait_dma", None)
        if wait:
            wait()

        w = area.x2 - area.x1 + 1
        h = area.y2 - area.y1 + 1
        size = w * h
        data_view = color_p.__dereference__(size * self.pixel_size)
        if self.rgb565_swap_func:
            self.rgb565_swap_func(data_view, size)

        disp.blit(area.x1, area.y1, w, h, data_view, is_blocking=False)
        disp_drv.flush_ready()

    def deinit(self):
        if self.disp_drv:
            self.disp_drv.delete()
            self.disp_drv = None

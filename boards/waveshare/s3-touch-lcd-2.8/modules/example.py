import board
import lvgl as lv

# ============================================================
# 1. 初始化主板
# ============================================================
board.init()
board.display.set_backlight(100)

# ============================================================
# 2. 构建 UI
# ============================================================
scr = lv.screen_active()

# ---------- 按钮 1 ----------
btn1 = lv.button(scr)
btn1.set_size(140, 60)
btn1.align(lv.ALIGN.TOP_MID, 0, 40)

label1 = lv.label(btn1)
label1.set_style_text_font(lv.font_puhui_20, 0)
label1.set_text("点我")
label1.center()


def btn1_event_cb(evt):
    code = evt.get_code()
    if code == lv.EVENT.CLICKED:
        print("[btn1] CLICKED")
    elif code == lv.EVENT.PRESSED:
        print("[btn1] PRESSED")
        label1.set_text("已点击!")
    elif code == lv.EVENT.RELEASED:
        print("[btn1] RELEASED")
        label1.set_text("点我")


btn1.add_event_cb(btn1_event_cb, lv.EVENT.ALL, None)

# ---------- 按钮 2 ----------
btn2 = lv.button(scr)
btn2.set_size(140, 60)
btn2.align(lv.ALIGN.TOP_MID, 0, 130)

label2 = lv.label(btn2)
label2.set_style_text_font(lv.font_puhui_16, 0)
label2.set_text("LED: 关")
label2.center()

led_state = [False]


def btn2_event_cb(evt):
    if evt.get_code() == lv.EVENT.CLICKED:
        led_state[0] = not led_state[0]
        print("[btn2] LED =", "开" if led_state[0] else "关")
        label2.set_text("LED: " + ("开" if led_state[0] else "关"))


btn2.add_event_cb(btn2_event_cb, lv.EVENT.CLICKED, None)

# ---------- 状态栏 ----------
status = lv.label(scr)
status.set_text("触摸测试就绪")
status.align(lv.ALIGN.BOTTOM_MID, 0, -20)

print("UI 构建完成，等待触摸事件...")

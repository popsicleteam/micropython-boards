import gc
import time

import boarddev
import camera
import espdl
import image

# ============================================================
# 板级初始化
# ============================================================
boarddev.camera_init()

# ============================================================
# 初始化AI
# ============================================================
width, height = boarddev.camera.framesize()
img_buf = bytearray(width * height * 2)
mv_buf = memoryview(img_buf)
img = image.Image(width, height, image.RGB565, buffer=mv_buf)
det = espdl.ESPDet("/rom/espdet_pico_224_224_face.espdl", score=0.2, nms=0.5)

# ============================================================
# 主循环
# ============================================================
frame_count = 0
last_fps_ms = time.ticks_ms()

gc.collect()
while True:
    # snapshot 把 fb 数据直接 memcpy 进 mv_buf，返回 True/False；
    # 数据已落在自己的 buffer 里，与相机 fb 生命周期解耦。
    if boarddev.camera.snapshot(buffer=mv_buf):
        for x, y, w, h, score, category in det.detect(img):
            img.draw_rectangle(x, y, w, h, color=255, thickness=1)
            print("%.2f:%d" % (score, category))

        frame_count += 1

    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, last_fps_ms)
    if elapsed >= 1000:
        print("FPS: %.1f" % (frame_count * 1000.0 / elapsed))
        frame_count = 0
        last_fps_ms = now

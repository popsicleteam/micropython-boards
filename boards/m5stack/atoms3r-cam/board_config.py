import time

import camera
from machine import Pin

cam_en_pin = Pin("CAM_EN", Pin.OUT, value=1)


def camera_init(framesize=camera.FRAME_QVGA, flip=0, mirror=0, **kwargs):
    cam_en_pin.value(0)
    time.sleep_ms(500)
    try:
        camera.init(
            framesize=framesize,
            d0=3,
            d1=42,
            d2=46,
            d3=48,
            d4=4,
            d5=17,
            d6=11,
            d7=13,
            vsync=10,
            href=14,
            pclk=40,
            xclk=21,
            sda=12,
            scl=9,
            **kwargs,
        )
        camera.flip(flip)
        camera.mirror(mirror)
        return camera
    except Exception as e:
        camera_deinit()
        print("Camera initialization failed", e)
    return False


def camera_deinit():
    if not camera.deinit():
        return False
    cam_en_pin.value(1)
    return True

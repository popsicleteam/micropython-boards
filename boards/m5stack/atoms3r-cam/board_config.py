import time

import camera as _camera
from machine import Pin

cam_en_pin = Pin("CAM_EN", Pin.OUT, value=1)


def camera_init(flip=0, mirror=0, **kwargs):
    cam_en_pin.value(0)
    time.sleep_ms(500)
    try:
        _camera.init(
            framesize=_camera.FRAME_QVGA,
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
        _camera.flip(flip)
        _camera.mirror(mirror)
        return _camera
    except Exception as e:
        camera_deinit()
        print("Camera initialization failed", e)
    return False


def camera_deinit():
    try:
        _camera.deinit()
    except Exception:
        return False
    cam_en_pin.value(1)
    return True

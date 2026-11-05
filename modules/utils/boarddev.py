try:
    import board_config
except ImportError:

    class board_config:
        pass


try:
    from lv_display import lv_display_register
except ImportError:
    lv_display_register = None


try:
    from lv_touch import lv_touch_register
except ImportError:
    lv_touch_register = None


_devices = {}

# 注册 LVGL 屏幕和触摸输入
if lv_display_register is not None:
    _devices["display"] = lv_display_register(
        getattr(board_config, "display", None),
        getattr(board_config, "display_doublebuffer", True),
        getattr(board_config, "display_factor", 4),
    )
if lv_touch_register is not None:
    _devices["touch"] = lv_touch_register(
        getattr(board_config, "touch", None),
        getattr(board_config, "touch_max_point", None),
    )


def __getattr__(name):
    attr = getattr(board_config, name, None)
    if attr is None or str(type(attr)) == "<class 'module'>":
        if _devices.get(name, None):
            return _devices[name]
        return None

    if name.endswith("_init"):
        key = name[: -len("_init")]

        def init(*args, **kwargs):
            if _devices.get(key, None):
                return True
            rst = attr(*args, **kwargs)
            if rst:
                _devices[key] = rst
            return False

        return init

    if name.endswith("_deinit"):
        key = name[: -len("_deinit")]

        def deinit(*args, **kwargs):
            if _devices.get(key, None):
                attr(*args, **kwargs)
                _devices.pop(key)

        return deinit

    return attr

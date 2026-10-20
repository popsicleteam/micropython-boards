try:
    import board_config
except ImportError:

    class board_config:
        pass


_devices = {}


def __getattr__(name):
    attr = getattr(board_config, name, None)
    if attr is None:
        if _devices.get(name, None):
            return _devices[name]
        return None

    if not callable(attr):
        return attr

    if name.endswith("_init"):
        key = name[: -len("_init")]

        def init(*args, **kwargs):
            if _devices.get(key, None):
                return True
            rst = attr(*args, **kwargs)
            if rst:
                _devices[key] = rst
            return bool(rst)

        return init

    if name.endswith("_deinit"):
        key = name[: -len("_deinit")]

        def deinit(*args, **kwargs):
            if _devices.get(key, None):
                rst = attr(*args, **kwargs)
                if rst:
                    _devices[key] = None
                return bool(rst)
            return False

        return deinit

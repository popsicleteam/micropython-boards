# ft6x36.py —— 纯 MicroPython 驱动


class FT6X36:
    max_points = 2

    def __init__(
        self,
        i2c_bus,
        addr=0x38,
        width=-1,
        height=-1,
        inv_x=False,
        inv_y=False,
        swap_xy=False,
    ):
        self.i2c = i2c_bus
        self.addr = addr
        self.width, self.height = width, height
        self.inv_x, self.inv_y, self.swap_xy = inv_x, inv_y, swap_xy

        self.presses = 0
        self.points = [{"x": 0, "y": 0} for _ in range(self.max_points)]

        try:
            print(
                "FT6X36 touch IC ready (fw id 0x{0:X} rel {1:d}, lib {2:X})".format(
                    int.from_bytes(self.i2c.readfrom_mem(self.addr, 0xA6, 1), "big"),
                    int.from_bytes(self.i2c.readfrom_mem(self.addr, 0xAF, 1), "big"),
                    int.from_bytes(self.i2c.readfrom_mem(self.addr, 0xA1, 2), "big"),
                )
            )
            self.ok = True
        except Exception:
            print("FT6X36 touch IC not responding")
            self.ok = False

    def _parse_point(self, b, o):
        x = (b[o] << 8 | b[o + 1]) & 0x0FFF
        y = (b[o + 2] << 8 | b[o + 3]) & 0x0FFF
        if (self.width != -1 and x >= self.width) or (
            self.height != -1 and y >= self.height
        ):
            raise ValueError
        x = self.width - x - 1 if self.inv_x else x
        y = self.height - y - 1 if self.inv_y else y
        if self.swap_xy:
            x, y = y, x
        return (x, y)

    def read_touch(self):
        try:
            b = self.i2c.readfrom_mem(self.addr, 2, 11)
        except Exception:
            return None
        presses = b[0]
        if presses == 0 or presses > 2:
            self.presses = 0
            return (0, [])
        try:
            coords = [self._parse_point(b, 1)]
            if presses == 2:
                coords.append(self._parse_point(b, 7))
        except ValueError:
            self.presses = 0
            return (0, [])
        # 硬件 b[3] 高半字节提示两点需交换
        if (b[3] >> 4) and len(coords) == 2:
            coords[0], coords[1] = coords[1], coords[0]
        self.presses = presses
        for i, (x, y) in enumerate(coords):
            self.points[i]["x"], self.points[i]["y"] = x, y
        return (presses, coords)

    def deinit(self):
        pass

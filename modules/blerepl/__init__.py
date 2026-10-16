import io
import os

import bluetooth

from micropython import const

try:
    from bleuart import BLEUART
except ImportError:
    from .bleuart_peripheral import BLEUART


__all__ = ("start", "stop")

_MP_STREAM_POLL = const(3)
_MP_STREAM_POLL_RD = const(0x0001)

# 全局变量，用于跟踪当前活动的 BLE REPL 实例
_current_bleuart = None
_current_stream = None


class BLEUARTStream(io.IOBase):
    def __init__(self, uart):
        self._uart = uart
        self._uart.irq(self._on_rx)

    def _on_rx(self, _):
        # 对于某些平台（ESP32）需要主动通知 dupterm 有新数据
        if hasattr(os, "dupterm_notify"):
            os.dupterm_notify(None)

    def read(self, sz=None):
        data = self._uart.read(sz)
        return data

    def readinto(self, buf):
        # 非阻塞：有数据就填充，否则返回 None
        if self._uart.any():
            n = min(len(buf), self._uart.any())
            data = self._uart.read(n)
            buf[:n] = data
            return n
        return None

    def write(self, data):
        # dupterm 要求 write 必须返回写入字节数
        self._uart.write(data)
        return len(data)

    def ioctl(self, op, arg):
        if op == _MP_STREAM_POLL:
            if self._uart.any():
                return _MP_STREAM_POLL_RD
        return 0


def start(name=None):
    """
    启动 BLE REPL 服务。
    name: 广播时显示的设备名（默认为 "ble-repl"）
    返回 BLEUART 实例。
    """
    global _current_bleuart, _current_stream

    # 如果已有活动的 BLE REPL，直接返回
    if _current_bleuart is not None:
        return _current_bleuart

    ble = bluetooth.BLE()
    if name is None:
        name = "ble-repl"
    uart = BLEUART(ble, name=name)

    def bleuart_handler(event, data):
        global _current_bleuart
        if _current_bleuart:
            _current_bleuart.handle_irq(event, data)
        return None

    try:
        # 将 bleuart 的 irq handler 添加到 aioble 中
        import asyncio

        from aioble import core, peripheral

        core.register_irq_handler(bleuart_handler, None)
        peripheral._connect_event = (
            peripheral._connect_event or asyncio.ThreadSafeFlag()
        )
    except:
        pass

    stream = BLEUARTStream(uart)
    os.dupterm(stream)

    _current_bleuart = uart
    _current_stream = stream
    return uart


def stop():
    """
    停止当前 BLE REPL 服务。
    移除 dupterm，关闭蓝牙连接，并停止广播。
    """
    global _current_bleuart, _current_stream

    if _current_bleuart is None:
        return  # 没有活动实例，无需操作

    # 移除 dupterm，恢复标准 REPL
    try:
        os.dupterm(None)
    except Exception:
        pass

    # 关闭 BLE UART 服务（会断开连接、停止广播）
    try:
        _current_bleuart.close()
    except Exception:
        pass

    _current_bleuart = None
    _current_stream = None

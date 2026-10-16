import time

import bluetooth

from micropython import const

from .ble_advertising import advertising_payload

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_UART_SERVICE_UUID = bluetooth.UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
_UART_TX_CHAR_UUID = bluetooth.UUID("6e400003-b5a3-f393-e0a9-e50e24dcca9e")
_UART_RX_CHAR_UUID = bluetooth.UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")

_ADV_APPEARANCE_GENERIC_COMPUTER = const(128)


class BLEUART:
    def __init__(self, ble, name="ble-uart", rxbuf=256):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self.handle_irq)

        # 注册服务
        self._services = (
            _UART_SERVICE_UUID,
            (
                (_UART_TX_CHAR_UUID, _FLAG_READ | _FLAG_NOTIFY),
                (_UART_RX_CHAR_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),
            ),
        )
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services(
            (self._services,)
        )
        self._ble.gatts_set_buffer(self._rx_handle, rxbuf, True)

        self._connections = set()
        self._rx_buffer = bytearray()
        self._handler = None  # 用户回调（on_rx）

        # 构建广告数据
        self._payload = advertising_payload(
            name=name,
            services=[_UART_SERVICE_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_COMPUTER,
        )
        self._advertise()

    def irq(self, handler):
        """设置数据接收回调：handler() 在有新数据时被调用"""
        self._handler = handler

    def handle_irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            self._advertise()  # 重新开始广播
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle and conn_handle in self._connections:
                new_data = self._ble.gatts_read(self._rx_handle)
                self._rx_buffer += new_data
                # 通知上层有数据到达
                if self._handler:
                    self._handler()

    def any(self):
        return len(self._rx_buffer)

    def read(self, sz=None):
        if not sz:
            sz = len(self._rx_buffer)
        result = self._rx_buffer[:sz]
        self._rx_buffer = self._rx_buffer[sz:]
        return result

    def write(self, data):
        if not self._connections:
            return
        chunk_size = 64
        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            for conn_handle in self._connections:
                try:
                    self._ble.gatts_notify(conn_handle, self._tx_handle, chunk)
                    time.sleep_ms(10)
                except Exception:
                    # 连接可能已断开，忽略错误
                    pass

    def close(self):
        for conn_handle in self._connections:
            try:
                self._ble.gap_disconnect(conn_handle)
            except:
                pass
        self._connections.clear()
        self._ble.active(False)

    def _advertise(self, interval_us=500000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

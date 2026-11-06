"""
XL9535QF24 16 位 I2C GPIO 扩展器 MicroPython 驱动。

支持芯片：
    - XL9535（XINLUDA）
    - PCA9535 / PCA9535C（TI/NXP，寄存器完全兼容）
    - TCA9555（TI，寄存器兼容，额外 INT 输出配置寄存器未使用）

依赖：
    - micropython（const）
    - machine（I2C、Pin，由调用方注入）
    - time（sleep_ms，仅内部 I2C 重试使用）

兼容性：
    - MicroPython v1.19+（未使用 f-string，向下兼容旧固件）
    - 不依赖 typing / dataclasses / abc / enum / warnings / logging
    - 不使用运行时类型注解

引脚编号约定：
    0..7   → Port0（P00..P07）
    10..17 → Port1（P10..P17）
    8、9   → 非法（不对应任何引脚，抛 ValueError）

    说明：编号与芯片丝印 P00-P07 / P10-P17 的十位/个位一致，
    跳过 8、9 是为了让 pin_mode(10) 直观对应 P10，避免 (8→P10)
    这种反直觉映射。

中断（INT）支持：
    - XL9535 的 INT 引脚为开漏、低电平有效，**必须在硬件上接上拉电阻**
      （推荐 4.7kΩ-10kΩ），否则会产生大量假中断。
    - 构造函数必须传入 int_pin（MCU 端已配置好的 machine.Pin）；
      未传则 is_interrupt_available 为 False，任何中断 API 抛
      RuntimeError("interrupt not enabled: no int_pin configured")。
    - 中断清除语义：**读清除**。读取某端口的 INPUT 寄存器即清除该端口
      对应的 INT 状态。端口 0 与端口 1 的中断相互独立。
    - 多路引脚共享单 INT 引脚：ISR 读两端口 INPUT 快照，按位变化分发
      给该引脚注册的回调。
    - 回调签名：fn(pin, port_state)
        pin        (int)  触发的 XL9535 引脚号（0..7 或 10..17）
        port_state (int)  该引脚所在端口的 8 位输入快照 0-255
      回调在 Pin.irq 指定的上下文执行：hard=True 时在硬中断上下文，
      hard=False 时在调度器上下文。驱动内不阻塞，但**用户回调自身**
      若在 hard=True 下做 I2C / print 会失败，责任在用户。
    - 错误通道：ISR 内捕获的异常存入 self.last_error；若提供 error_handler，
      则以 error_handler(exc) 形式通知。用户回调自身异常走同一通道。
"""

import time

from machine import Pin

from micropython import const

# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------

_REG_INPUT_PORT0 = const(0x00)
_REG_INPUT_PORT1 = const(0x01)
_REG_OUTPUT_PORT0 = const(0x02)
_REG_OUTPUT_PORT1 = const(0x03)
_REG_POLARITY_INV0 = const(0x04)
_REG_POLARITY_INV1 = const(0x05)
_REG_CONFIG_PORT0 = const(0x06)
_REG_CONFIG_PORT1 = const(0x07)

_XL9535_I2C_ADDR_DEFAULT = const(0x20)
_XL9535_I2C_ADDR_MIN = const(0x20)
_XL9535_I2C_ADDR_MAX = const(0x27)

DIR_INPUT = const(1)
DIR_OUTPUT = const(0)

_BYTE_MASK = const(0xFF)

_POWER_ON_CONFIG = const(0xFF)
_POWER_ON_OUTPUT = const(0x00)
_POWER_ON_POLARITY = const(0x00)

_INPUT_REG = (_REG_INPUT_PORT0, _REG_INPUT_PORT1)
_OUTPUT_REG = (_REG_OUTPUT_PORT0, _REG_OUTPUT_PORT1)
_CONFIG_REG = (_REG_CONFIG_PORT0, _REG_CONFIG_PORT1)
_POLARITY_REG = (_REG_POLARITY_INV0, _REG_POLARITY_INV1)

# 引脚编号范围（v1.3.0：跳过 8、9）
_PIN_PORT0_MIN = const(0)
_PIN_PORT0_MAX = const(7)
_PIN_PORT1_MIN = const(10)
_PIN_PORT1_MAX = const(17)


# ---------------------------------------------------------------------------
# 驱动类
# ---------------------------------------------------------------------------


class XL9535:
    """
    XL9535QF24 16 位 I2C GPIO 扩展器驱动。

    引脚编号约定：
        0..7   → Port0（P00..P07）
        10..17 → Port1（P10..P17）
        8、9   → 非法（ValueError）

    中断使用（推荐流程）：
        1. 硬件：XL9535 INT → MCU GPIO，中间 4.7kΩ-10kΩ 上拉到 VCC。
        2. 构造：xl = XL9535(i2c, int_pin=Pin(4, Pin.IN, Pin.PULL_UP))
        3. 配置要监测的引脚为输入：xl.pin_mode(10, DIR_INPUT)  # P10
        4. 绑定回调：xl.attach_interrupt(10, on_p10, trigger=Pin.IRQ_BOTH)
        5. ISR 读两端口快照 → 按位分发给已注册回调。

    不变量：
        - deinit() 后所有 I2C / 中断方法抛 RuntimeError。
        - 构造时未传 int_pin → is_interrupt_available 为 False，
          所有中断 API 抛 RuntimeError("interrupt not enabled ...")。
        - attach_interrupt(pin) 重复调用同一 pin：覆盖旧回调与 trigger。
        - detach_interrupt() 幂等；解绑后 is_interrupt_attached 为 False。
        - deinit() 自动解绑所有中断（§6.6）。
    """

    __slots__ = (
        "_i2c",
        "_address",
        "_buf1",
        "_buf2",
        "_retries",
        "_retry_delay_ms",
        "_int_pin",
        "_int_callbacks",  # dict: pin(int) -> (callback, trigger)
        "_int_last_state",  # dict: port(int) -> 上次快照(int)，用于边沿判定
        "_irq_bound",
        "_error_handler",
        "_last_error",
    )

    def __init__(
        self,
        i2c,
        address=_XL9535_I2C_ADDR_DEFAULT,
        retries=2,
        retry_delay_ms=5,
        int_pin=None,
        error_handler=None,
    ):
        """
        Args:
            i2c: 已初始化的 machine.I2C 或 machine.SoftI2C 对象。
            address (int): 7 位 I2C 地址 0x20-0x27，默认 0x20。
            retries (int): I2C 失败重试次数，默认 2。
            retry_delay_ms (int): 重试间隔毫秒，默认 5。
            int_pin (machine.Pin|None): MCU 端已连接到 XL9535 INT 引脚
                的 machine.Pin 对象。调用方负责：
                    - 硬件上拉 4.7kΩ-10kΩ；
                    - Pin 模式设为 Pin.IN（建议 Pin.PULL_UP）；
                    - 构造时不要预先绑定 irq（由 attach_interrupt 绑定）。
                None（默认）表示不使用中断功能：所有中断 API 抛
                RuntimeError。如需启用，请传入。
            error_handler (callable|None): 错误通知回调，签名 fn(exc)。
                被 ISR / 用户回调 / I2C 重试耗尽时的异常调用（§7.1）。

        Raises:
            ValueError: address 越界，或 retries < 0。
            TypeError: int_pin 非 None 且非 Pin，或 error_handler 非法。
            OSError: 设备在指定地址无响应。
        """
        if not (_XL9535_I2C_ADDR_MIN <= address <= _XL9535_I2C_ADDR_MAX):
            raise ValueError(
                "address must be in range 0x%02X-0x%02X"
                % (_XL9535_I2C_ADDR_MIN, _XL9535_I2C_ADDR_MAX)
            )
        if retries < 0:
            raise ValueError("retries must be >= 0")
        if int_pin is not None and not isinstance(int_pin, Pin):
            raise TypeError("int_pin must be a machine.Pin or None")
        if error_handler is not None and not callable(error_handler):
            raise TypeError("error_handler must be callable or None")

        self._i2c = i2c
        self._address = address
        self._buf1 = bytearray(1)
        self._buf2 = bytearray(2)
        self._retries = retries
        self._retry_delay_ms = retry_delay_ms

        self._int_pin = int_pin
        self._int_callbacks = {}  # pin(int) -> (cb, trigger)
        self._int_last_state = {0: -1, 1: -1}  # 无效初始值，首次必触发
        self._irq_bound = False

        self._error_handler = error_handler
        self._last_error = None

        # 可访问性探测
        try:
            self._i2c.readfrom_mem_into(self._address, _REG_CONFIG_PORT0, self._buf1)
        except OSError:
            self._i2c = None
            raise OSError("XL9535 not responding at I2C address 0x%02X" % address)

        self.reset()

    # ------------------------------------------------------------------
    # 内部 I2C 原语
    # ------------------------------------------------------------------

    def _i2c_write(self, reg, buf):
        last_exc = None
        for attempt in range(self._retries + 1):
            try:
                self._i2c.writeto_mem(self._address, reg, buf)
                return
            except OSError as exc:
                last_exc = exc
                if attempt < self._retries:
                    time.sleep_ms(self._retry_delay_ms)
        raise last_exc

    def _i2c_read_into(self, reg, buf):
        last_exc = None
        for attempt in range(self._retries + 1):
            try:
                self._i2c.readfrom_mem_into(self._address, reg, buf)
                return
            except OSError as exc:
                last_exc = exc
                if attempt < self._retries:
                    time.sleep_ms(self._retry_delay_ms)
        raise last_exc

    def _write_reg(self, reg, value):
        self._buf1[0] = value & _BYTE_MASK
        self._i2c_write(reg, self._buf1)

    def _read_reg(self, reg):
        self._i2c_read_into(reg, self._buf1)
        return self._buf1[0]

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------

    def _check_alive(self):
        if self._i2c is None:
            raise RuntimeError("device is deinitialized")

    def _check_interrupt_enabled(self):
        if self._int_pin is None:
            raise RuntimeError("interrupt not enabled: no int_pin configured")

    @staticmethod
    def _check_port(port):
        if not isinstance(port, int):
            raise TypeError("port must be int")
        if port not in (0, 1):
            raise ValueError("port must be 0 or 1")

    @staticmethod
    def _check_byte(value, name="value"):
        if not isinstance(value, int):
            raise TypeError("%s must be int" % name)
        if not (0 <= value <= _BYTE_MASK):
            raise ValueError("%s must be in range 0-255" % name)

    @staticmethod
    def _check_word(value, name="value"):
        if not isinstance(value, int):
            raise TypeError("%s must be int" % name)
        if not (0 <= value <= 0xFFFF):
            raise ValueError("%s must be in range 0x0000-0xFFFF" % name)

    @staticmethod
    def _normalize_pin(pin):
        """
        校验并归一化 XL9535 引脚号。

        合法范围（v1.3.0）：
            0..7   → P00..P07（Port0）
            10..17 → P10..P17（Port1）
            8、9   → 非法（不对应任何引脚）

        Raises:
            TypeError: pin 非 int。
            ValueError: pin 落在 8、9 或超出 0..17 范围。
        """
        if not isinstance(pin, int):
            raise TypeError("pin must be int")
        if _PIN_PORT0_MIN <= pin <= _PIN_PORT0_MAX:
            return pin
        if _PIN_PORT1_MIN <= pin <= _PIN_PORT1_MAX:
            return pin
        raise ValueError(
            "pin must be 0-7 (P00-P07) or 10-17 (P10-P17); 8 and 9 are invalid"
        )

    @staticmethod
    def _pin_to_port_bit(pin):
        """
        引脚号 → (port, bit)。调用方必须先 _normalize_pin()。
            0..7   → (0, pin)
            10..17 → (1, pin - 10)
        """
        if pin < _PIN_PORT1_MIN:
            return 0, pin
        return 1, pin - _PIN_PORT1_MIN

    # ------------------------------------------------------------------
    # 错误通道（§7.1）
    # ------------------------------------------------------------------

    def _notify_error(self, exc):
        self._last_error = exc
        handler = self._error_handler
        if handler is not None:
            try:
                handler(exc)
            except Exception as nested:
                self._last_error = nested

    @property
    def last_error(self):
        """最近一次错误（Exception 或 None）。"""
        return self._last_error

    def clear_last_error(self):
        """手动清空 last_error。"""
        self._last_error = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def reset(self):
        """
        复位到上电默认状态：全输入、输出清零、极性不反转。
        保留 IRQ 绑定与回调列表（§5.7）。
        """
        self._check_alive()
        self._write_reg(_REG_OUTPUT_PORT0, _POWER_ON_OUTPUT)
        self._write_reg(_REG_OUTPUT_PORT1, _POWER_ON_OUTPUT)
        self._write_reg(_REG_POLARITY_INV0, _POWER_ON_POLARITY)
        self._write_reg(_REG_POLARITY_INV1, _POWER_ON_POLARITY)
        self._write_reg(_REG_CONFIG_PORT0, _POWER_ON_CONFIG)
        self._write_reg(_REG_CONFIG_PORT1, _POWER_ON_CONFIG)

    def deinit(self):
        """
        释放资源。幂等。

        - 自动 detach_interrupt()（解绑所有引脚回调 + MCU IRQ）。
        - 不关闭 i2c 总线。
        - 不改变 XL9535 芯片寄存器状态。
        - deinit() 后任何 I2C / 中断方法抛 RuntimeError。
        """
        if self._i2c is None:
            return
        self.detach_interrupt()
        self._i2c = None
        self._error_handler = None

    @property
    def is_deinitialized(self):
        """bool: True 表示 deinit() 已被调用。"""
        return self._i2c is None

    # ------------------------------------------------------------------
    # 端口级 / 引脚级操作
    # ------------------------------------------------------------------

    def write_port(self, port, value):
        """向端口写入 8 位输出锁存值。Args: port(0|1), value(0-255)。"""
        self._check_alive()
        self._check_port(port)
        self._check_byte(value)
        self._write_reg(_OUTPUT_REG[port], value)

    def read_port(self, port):
        """
        读取端口 8 位输入电平。实时读取，不缓存。
        读取即清除该端口 INT 状态（§5.6 读清除）。
        """
        self._check_alive()
        self._check_port(port)
        return self._read_reg(_INPUT_REG[port])

    def set_port_direction(self, port, direction_byte):
        """配置端口方向。direction_byte 每 bit：1=输入，0=输出。"""
        self._check_alive()
        self._check_port(port)
        self._check_byte(direction_byte, "direction_byte")
        self._write_reg(_CONFIG_REG[port], direction_byte)

    def set_port_polarity(self, port, polarity_byte):
        """配置端口输入极性反转。仅影响 INPUT 读数。"""
        self._check_alive()
        self._check_port(port)
        self._check_byte(polarity_byte, "polarity_byte")
        self._write_reg(_POLARITY_REG[port], polarity_byte)

    def pin_mode(self, pin, mode):
        """
        配置单个引脚方向。

        Args:
            pin (int): 0..7（P00-P07）或 10..17（P10-P17）；8、9 非法。
            mode (int): DIR_INPUT | DIR_OUTPUT。
        """
        self._check_alive()
        pin = self._normalize_pin(pin)
        if mode not in (DIR_INPUT, DIR_OUTPUT):
            raise ValueError("mode must be DIR_INPUT or DIR_OUTPUT")
        port, bit = self._pin_to_port_bit(pin)
        reg = _CONFIG_REG[port]
        current = self._read_reg(reg)
        if mode == DIR_INPUT:
            current |= 1 << bit
        else:
            current &= ~(1 << bit)
        self._write_reg(reg, current)

    def digital_write(self, pin, value):
        """
        设置单个引脚输出锁存电平。

        Args:
            pin (int): 0..7 或 10..17。
            value (bool): True=高，False=低。
        """
        self._check_alive()
        pin = self._normalize_pin(pin)
        port, bit = self._pin_to_port_bit(pin)
        reg = _OUTPUT_REG[port]
        current = self._read_reg(reg)
        if value:
            current |= 1 << bit
        else:
            current &= ~(1 << bit)
        self._write_reg(reg, current)

    def digital_read(self, pin):
        """
        读取单个引脚输入电平，返回 bool。读取即清除该端口 INT。

        Args:
            pin (int): 0..7 或 10..17。
        """
        self._check_alive()
        pin = self._normalize_pin(pin)
        port, bit = self._pin_to_port_bit(pin)
        value = self._read_reg(_INPUT_REG[port])
        return bool(value & (1 << bit))

    def toggle(self, pin):
        """
        翻转单个引脚输出锁存（读 OUTPUT 寄存器，不受极性影响）。

        Args:
            pin (int): 0..7 或 10..17。
        """
        self._check_alive()
        pin = self._normalize_pin(pin)
        port, bit = self._pin_to_port_bit(pin)
        reg = _OUTPUT_REG[port]
        current = self._read_reg(reg)
        current ^= 1 << bit
        self._write_reg(reg, current)

    def write_all(self, value):
        """一次写 16 位输出锁存（低字节→Port0，高字节→Port1）。"""
        self._check_alive()
        self._check_word(value)
        self._buf2[0] = value & _BYTE_MASK
        self._buf2[1] = (value >> 8) & _BYTE_MASK
        self._i2c_write(_REG_OUTPUT_PORT0, self._buf2)

    def read_all(self):
        """一次读 16 位输入。读取即清除两端口 INT。"""
        self._check_alive()
        self._i2c_read_into(_REG_INPUT_PORT0, self._buf2)
        return self._buf2[0] | (self._buf2[1] << 8)

    def set_all_direction(self, direction_word):
        """一次配置 16 位方向。bit=1 输入，bit=0 输出。"""
        self._check_alive()
        self._check_word(direction_word, "direction_word")
        self._buf2[0] = direction_word & _BYTE_MASK
        self._buf2[1] = (direction_word >> 8) & _BYTE_MASK
        self._i2c_write(_REG_CONFIG_PORT0, self._buf2)

    # ------------------------------------------------------------------
    # 中断（INT）支持
    # ------------------------------------------------------------------

    @property
    def is_interrupt_available(self):
        """bool: True 表示构造时传入了 int_pin，中断功能可用。"""
        return self._int_pin is not None

    @property
    def is_interrupt_attached(self):
        """bool: True 表示至少有一个 XL 引脚绑定了中断回调。"""
        return len(self._int_callbacks) > 0

    def attach_interrupt(self, pin, callback, trigger=Pin.IRQ_FALLING):
        """
        将 XL9535 引脚 `pin` 的中断绑定到 `callback`。

        硬件只有一个 INT 引脚，多个 XL 引脚共享。ISR 读两端口输入快照，
        按 trigger 判定每个已注册引脚是否触发，命中则调用该引脚的 callback。

        Args:
            pin (int): XL9535 引脚号：
                0..7   → P00..P07
                10..17 → P10..P17
                8、9   → ValueError
            callback (callable): fn(pin, port_state)
                pin (int)        触发的 XL 引脚号（0..7 或 10..17）
                port_state (int) 该引脚所在端口的 8 位快照 0-255
                在 Pin.irq 指定上下文执行（hard=True 时为硬中断，
                hard=False 时为调度器）。
            trigger (int): 支持以下值：
                Pin.IRQ_FALLING    下降沿（默认）
                Pin.IRQ_RISING     上升沿
                Pin.IRQ_BOTH       任意边沿
                Pin.IRQ_LOW_LEVEL  低电平
                Pin.IRQ_HIGH_LEVEL 高电平
                电平触发模式下，ISR 在电平持续期间可能反复触发；
                用户回调需自行处理去抖/状态机。XL9535 INT 为低有效，
                推荐 IRQ_FALLING 或 IRQ_BOTH。

        Raises:
            RuntimeError: 已 deinit()，或未配置 int_pin。
            TypeError: pin 非 int，或 callback 不可调用。
            ValueError: pin 为 8/9 或越界，或 trigger 非法。

        副作用：
            - 调用前请确保该 XL 引脚已 pin_mode(DIR_INPUT)，否则输出
              状态变化不会触发 INT。
            - 首次 attach 时自动在 int_pin 上绑定 IRQ_BOTH（软中断）。
            - trigger 是 **每个引脚** 独立的软件过滤条件；MCU 端 IRQ 沿
              固定为 IRQ_BOTH，软件层按引脚 trigger 过滤。这样多引脚
              不同 trigger 可共存。

        幂等：
            - 同一 pin 重复 attach：覆盖旧 callback 与 trigger。
            - 不影响其他 pin 的绑定。
        """
        self._check_alive()
        self._check_interrupt_enabled()
        pin = self._normalize_pin(pin)
        if not callable(callback):
            raise TypeError("callback must be callable")
        if trigger not in (
            Pin.IRQ_FALLING,
            Pin.IRQ_RISING,
            Pin.IRQ_BOTH,
            Pin.IRQ_LOW_LEVEL,
            Pin.IRQ_HIGH_LEVEL,
        ):
            raise ValueError("trigger must be a valid Pin.IRQ_* constant")

        self._int_callbacks[pin] = (callback, trigger)

        if not self._irq_bound:
            self._bind_hw_irq()

    def detach_interrupt(self, pin=None):
        """
        解绑 XL 引脚中断。

        Args:
            pin (int|None): None 解绑全部（同时解绑 MCU IRQ）；
                int 仅解绑该引脚；解绑最后一个引脚时自动解绑 MCU IRQ。

        Raises:
            RuntimeError: 已 deinit()。
            ValueError: pin 为 8/9 或越界。
            TypeError: pin 非 int 且非 None。

        幂等：解绑不存在的 pin 无副作用。
        """
        self._check_alive()
        if pin is None:
            self._int_callbacks.clear()
        else:
            pin = self._normalize_pin(pin)
            self._int_callbacks.pop(pin, None)

        if not self._int_callbacks:
            self._unbind_hw_irq()

    def clear_interrupt(self):
        """
        显式清除 XL9535 的中断状态（读清除语义）。

        实现：依次读 Port0、Port1 的 INPUT 寄存器。INT 引脚被释放。

        适用：
            - hard=True 模式下，ISR 只置标志，主循环需主动清除；
            - 调试残留 INT。
        """
        self._check_alive()
        self._read_reg(_REG_INPUT_PORT0)
        self._read_reg(_REG_INPUT_PORT1)

    # ------------------------------------------------------------------
    # IRQ 绑定 / 解绑（内部）
    # ------------------------------------------------------------------

    def _bind_hw_irq(self):
        """在 MCU 端绑定 IRQ。trigger 固定 IRQ_BOTH，软中断。"""
        try:
            self._int_pin.irq(
                trigger=Pin.IRQ_BOTH,
                handler=self._make_isr(),
                hard=False,
            )
        except Exception as exc:
            self._notify_error(exc)
            raise
        self._irq_bound = True

    def _unbind_hw_irq(self):
        """解绑 MCU 端 IRQ。幂等。"""
        if not self._irq_bound:
            return
        try:
            self._int_pin.irq(handler=None)
        except Exception as exc:
            self._notify_error(exc)
        self._irq_bound = False

    # ------------------------------------------------------------------
    # ISR 构造
    # ------------------------------------------------------------------

    def _make_isr(self):
        """
        软中断回调：读两端口快照，按每引脚 trigger 与上次状态比较，
        命中则调用该引脚回调。禁止抛异常、禁止字符串分配。
        """
        read_reg = self._read_reg
        input_reg0 = _INPUT_REG[0]
        input_reg1 = _INPUT_REG[1]
        callbacks = self._int_callbacks
        last_state = self._int_last_state
        notify_error = self._notify_error
        dispatch = self._dispatch_port

        def _isr(_pin_obj):
            try:
                state0 = read_reg(input_reg0)
                state1 = read_reg(input_reg1)
            except Exception as exc:
                notify_error(exc)
                return

            prev0 = last_state[0]
            last_state[0] = state0
            if prev0 != state0 or prev0 == -1:
                dispatch(0, state0, prev0, callbacks, notify_error)

            prev1 = last_state[1]
            last_state[1] = state1
            if prev1 != state1 or prev1 == -1:
                dispatch(1, state1, prev1, callbacks, notify_error)

        return _isr

    @staticmethod
    def _dispatch_port(port, state, prev, callbacks, notify_error):
        """
        按位遍历已注册引脚，命中 trigger 则调用回调。

        引脚号映射（v1.3.0）：
            Port0 bit 0..7 → 引脚号 0..7
            Port1 bit 0..7 → 引脚号 10..17
        """
        base_pin = _PIN_PORT0_MIN if port == 0 else _PIN_PORT1_MIN
        for bit in range(8):
            pin = base_pin + bit
            entry = callbacks.get(pin)
            if entry is None:
                continue
            cb, trigger = entry
            curr_bit = (state >> bit) & 1
            prev_bit = (prev >> bit) & 1 if prev != -1 else -1

            fired = False
            if trigger == Pin.IRQ_FALLING:
                fired = prev_bit == 1 and curr_bit == 0
            elif trigger == Pin.IRQ_RISING:
                fired = prev_bit == 0 and curr_bit == 1
            elif trigger == Pin.IRQ_BOTH:
                fired = prev_bit != -1 and prev_bit != curr_bit
            elif trigger == Pin.IRQ_LOW_LEVEL:
                fired = curr_bit == 0
            elif trigger == Pin.IRQ_HIGH_LEVEL:
                fired = curr_bit == 1

            if not fired:
                continue
            try:
                cb(pin, state)
            except Exception as exc:
                notify_error(exc)


# ---------------------------------------------------------------------------
# 使用示例（可直接粘贴到 MicroPython REPL）
# ---------------------------------------------------------------------------
#
# from machine import I2C, Pin
# from xl9535 import XL9535, DIR_INPUT, DIR_OUTPUT
# import time
#
# i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400_000)
#
# # 硬件：XL9535 INT → GPIO4，外接 10kΩ 上拉到 VCC
# int_pin = Pin(4, Pin.IN, Pin.PULL_UP)
# xl = XL9535(i2c, int_pin=int_pin)
#
# # ---- 示例 1：P00 作为输出，点亮 LED ----
# xl.pin_mode(0, DIR_OUTPUT)
# xl.digital_write(0, True)
#
# # ---- 示例 2：P10 作为输入（引脚号 10，不是 8）----
# xl.pin_mode(10, DIR_INPUT)
# print("P10 =", xl.digital_read(10))
#
# # ---- 示例 3：非法引脚号 8、9 ----
# try:
#     xl.pin_mode(8, DIR_INPUT)
# except ValueError as exc:
#     print("caught:", exc)          # pin must be 0-7 ... 8 and 9 are invalid
#
# # ---- 示例 4：INT 使用 ----
# xl.pin_mode(10, DIR_INPUT)    # P10
# xl.pin_mode(11, DIR_INPUT)    # P11
#
# def on_p10(pin, port_state):
#     print("P10 INT, port_state=0x%02X" % port_state)
#
# def on_p11(pin, port_state):
#     print("P11 INT, port_state=0x%02X" % port_state)
#
# xl.attach_interrupt(10, on_p10, trigger=Pin.IRQ_FALLING)
# xl.attach_interrupt(11, on_p11, trigger=Pin.IRQ_BOTH)
#
# # 单引脚解绑 / 全部解绑
# # xl.detach_interrupt(10)
# # xl.detach_interrupt()
#
# # 主循环轮询错误
# while True:
#     err = xl.last_error
#     if err is not None:
#         print("driver error:", err)
#         xl.clear_last_error()
#     time.sleep_ms(100)

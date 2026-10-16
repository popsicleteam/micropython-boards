import struct

import bluetooth

from micropython import const

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)

_ADV_MAX_PAYLOAD = const(31)


def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None):
    payload = bytearray()

    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    # 1. Flags (必须)
    _append(
        _ADV_TYPE_FLAGS,
        struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)),
    )

    # 2. 处理名字（如果提供）
    name_added = False
    if name:
        name_bytes = name
        name_block_len = len(name_bytes) + 2  # 2 = 长度字节 + 类型字节
        # 检查添加名字后是否超出限制
        if len(payload) + name_block_len > _ADV_MAX_PAYLOAD:
            # 超出：只保留 Flags + 截断的名字
            payload = bytearray()
            _append(
                _ADV_TYPE_FLAGS,
                struct.pack(
                    "B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)
                ),
            )
            remaining = _ADV_MAX_PAYLOAD - len(payload) - 2  # 减去名字头的2字节
            if remaining > 0:
                truncated_name = name_bytes[:remaining]
                _append(_ADV_TYPE_NAME, truncated_name)
            return payload
        else:
            _append(_ADV_TYPE_NAME, name_bytes)
            name_added = True

    # 3. 服务（仅在名字已添加且未超出的情况下考虑）
    if services and name_added:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                block_len = 2 + 2  # UUID长度2 + 类型长度1 + 长度字段1
            elif len(b) == 4:
                block_len = 4 + 2
            elif len(b) == 16:
                block_len = 16 + 2
            else:
                continue
            if len(payload) + block_len > _ADV_MAX_PAYLOAD:
                # 添加该服务会导致超出，则忽略所有后续服务
                return payload
            # 否则添加
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            else:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)

    # 4. 最终检查（正常情况下不会超出）
    if len(payload) > _ADV_MAX_PAYLOAD:
        raise ValueError("advertising payload too large")
    return payload


def decode_field(payload, adv_type):
    i = 0
    result = []
    while i + 1 < len(payload):
        if payload[i + 1] == adv_type:
            result.append(payload[i + 2 : i + payload[i] + 1])
        i += 1 + payload[i]
    return result


def decode_name(payload):
    n = decode_field(payload, _ADV_TYPE_NAME)
    return str(n[0], "utf-8") if n else ""


def decode_services(payload):
    services = []
    for code in (
        _ADV_TYPE_UUID16_COMPLETE,
        _ADV_TYPE_UUID32_COMPLETE,
        _ADV_TYPE_UUID128_COMPLETE,
    ):
        for u in decode_field(payload, code):
            services.append(bluetooth.UUID(u))
    return services

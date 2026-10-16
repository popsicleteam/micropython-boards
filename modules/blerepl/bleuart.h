#pragma once

#include "py/ringbuf.h"
#include "py/runtime.h"

#define BLEUART_MAX_NAME_LEN 27  // 设备名称最大字符数（含结尾\0）
#define ADV_MAX_PAYLOAD 31       // 广播数据最大长度（BLE 规范）

typedef struct _bleuart_obj_t {
  mp_obj_base_t base;
  mp_obj_t ble_obj;
  mp_obj_t callback;
  mp_obj_t cached_adv_payload;
  uint16_t tx_handle;
  uint16_t rx_handle;
  uint16_t conn_handle;
  ringbuf_t rx_buffer;
  uint8_t* buf_data;
  size_t buf_size;
  bool connected;
  bool closed;
  bool overflow;
  char dev_name[BLEUART_MAX_NAME_LEN];
  size_t dev_name_len;
} bleuart_obj_t;

extern const mp_obj_type_t bleuart_type;

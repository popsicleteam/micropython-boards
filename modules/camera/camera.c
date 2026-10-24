#include "camera.h"

#include <string.h>

#include "esp_camera.h"
#include "esp_log.h"
#include "esp_system.h"
#include "py/binary.h"
#include "py/nlr.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "spi_flash_mmap.h"

static const char* TAG = "CAMERA";

/* --------------------------------------------------------------------------
 * 共用校验：像素格式是否合法
 * -------------------------------------------------------------------------- */
static bool is_valid_format(int format) {
  return (format == PIXFORMAT_RGB565) || (format == PIXFORMAT_YUV422) || (format == PIXFORMAT_YUV420) || (format == PIXFORMAT_GRAYSCALE) ||
         (format == PIXFORMAT_JPEG) || (format == PIXFORMAT_RGB888) || (format == PIXFORMAT_RAW) || (format == PIXFORMAT_RGB444) ||
         (format == PIXFORMAT_RGB555) || (format == PIXFORMAT_RAW8);
}

/* --------------------------------------------------------------------------
 * camera.init(*)
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_init(mp_uint_t n_pos_args, const mp_obj_t* pos_args, mp_map_t* kw_args) {
  enum {
    ARG_format,
    ARG_framesize,
    ARG_quality,
    ARG_d0,
    ARG_d1,
    ARG_d2,
    ARG_d3,
    ARG_d4,
    ARG_d5,
    ARG_d6,
    ARG_d7,
    ARG_VSYNC,
    ARG_HREF,
    ARG_PCLK,
    ARG_PWDN,
    ARG_RESET,
    ARG_XCLK,
    ARG_I2CPORT,
    ARG_SIOD,
    ARG_SIOC,
    ARG_FREQ,
    ARG_FBSIZE,
    ARG_FBLOC,
  };

  static const mp_arg_t allowed_args[] = {
      {MP_QSTR_format, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = PIXFORMAT_RGB565}},
      {MP_QSTR_framesize, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = FRAMESIZE_QVGA}},
      {MP_QSTR_quality, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 12}},
      {MP_QSTR_d0, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d1, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d2, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d3, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d4, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d5, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d6, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_d7, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_vsync, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_href, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_pclk, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_pwdn, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_reset, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_xclk, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_i2c_port, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0}},
      {MP_QSTR_sda, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_scl, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
      {MP_QSTR_xclk_freq, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = XCLK_FREQ_20MHz}},
      {MP_QSTR_fb_count, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 2}},
      {MP_QSTR_fb_location, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = CAMERA_FB_IN_PSRAM}},
  };

  mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
  mp_arg_parse_all(n_pos_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

  /* 用 int 而非 int8_t，避免上游枚举扩展后溢出 */
  int format = args[ARG_format].u_int;
  if (!is_valid_format(format)) {
    mp_raise_ValueError(MP_ERROR_TEXT("Image format is not valid"));
  }

  int size = args[ARG_framesize].u_int;
  if (size < 0 || size >= FRAMESIZE_INVALID) {
    mp_raise_ValueError(MP_ERROR_TEXT("Image framesize is not valid"));
  }

  int32_t xclk_freq = args[ARG_FREQ].u_int;
  if ((xclk_freq != XCLK_FREQ_10MHz) && (xclk_freq != XCLK_FREQ_20MHz)) {
    mp_raise_ValueError(MP_ERROR_TEXT("xclk frequency is not valid"));
  }

  /* 用 {0} 初始化，未显式赋值的字段不会带栈垃圾值 */
  camera_config_t config = {0};
  config.pin_d0 = args[ARG_d0].u_int;
  config.pin_d1 = args[ARG_d1].u_int;
  config.pin_d2 = args[ARG_d2].u_int;
  config.pin_d3 = args[ARG_d3].u_int;
  config.pin_d4 = args[ARG_d4].u_int;
  config.pin_d5 = args[ARG_d5].u_int;
  config.pin_d6 = args[ARG_d6].u_int;
  config.pin_d7 = args[ARG_d7].u_int;
  config.pin_vsync = args[ARG_VSYNC].u_int;
  config.pin_href = args[ARG_HREF].u_int;
  config.pin_pclk = args[ARG_PCLK].u_int;
  config.pin_pwdn = args[ARG_PWDN].u_int;
  config.pin_reset = args[ARG_RESET].u_int;
  config.pin_xclk = args[ARG_XCLK].u_int;
  config.sccb_i2c_port = args[ARG_I2CPORT].u_int;
  config.pin_sscb_sda = args[ARG_SIOD].u_int;
  config.pin_sscb_scl = args[ARG_SIOC].u_int;
  config.pixel_format = (pixformat_t)format;
  config.jpeg_quality = args[ARG_quality].u_int;
  config.xclk_freq_hz = xclk_freq;
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.frame_size = (framesize_t)size;
  config.fb_count = args[ARG_FBSIZE].u_int;
  config.fb_location = args[ARG_FBLOC].u_int;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  /* 允许首次 init 时 deinit 失败（无实例可卸载），忽略返回值 */
  esp_camera_deinit();
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Camera Init Failed");
    mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("Camera Init Failed"));
    return mp_const_false;
  }
  return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(camera_init_obj, 0, camera_init);

/* --------------------------------------------------------------------------
 * camera.deinit()
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_deinit() {
  esp_err_t err = esp_camera_deinit();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Camera deinit Failed");
    return mp_const_false;
  }
  return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_deinit_obj, camera_deinit);

/* --------------------------------------------------------------------------
 * camera.snapshot()
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_snapshot() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    ESP_LOGE(TAG, "Camera Capture Failed");
    return mp_const_false;
  }

  mp_obj_t image = mp_obj_new_bytes(fb->buf, fb->len);

  esp_camera_fb_return(fb);
  return image;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_snapshot_obj, camera_snapshot);

/* --------------------------------------------------------------------------
 * camera.jpeg([quality])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_jpeg(size_t n_pos_args, const mp_obj_t* pos_args, mp_map_t* kw_args) {
  enum { ARG_quality };
  static const mp_arg_t allowed_args[] = {
      {MP_QSTR_quality, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1}},
  };
  mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
  mp_arg_parse_all(n_pos_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

  int quality_arg = args[ARG_quality].u_int;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    ESP_LOGE(TAG, "Camera snapshot Failed");
    return mp_const_false;
  }

  mp_obj_t image;

  if (fb->format == PIXFORMAT_JPEG) {
    image = mp_obj_new_bytes(fb->buf, fb->len);
  } else {
    int quality;
    if (quality_arg >= 0) {
      if (quality_arg > 63) quality_arg = 63;
      quality = 100 - quality_arg;
    } else {
      sensor_t* s = esp_camera_sensor_get();
      if (s != NULL) {
        quality = 100 - s->status.quality;
      } else {
        quality = 80;
      }
    }

    uint8_t* jpg_buf = NULL;
    size_t jpg_len = 0;
    bool converted = frame2jpg(fb, quality, &jpg_buf, &jpg_len);
    if (!converted || jpg_buf == NULL) {
      ESP_LOGE(TAG, "JPEG conversion failed");
      esp_camera_fb_return(fb);
      return mp_const_false;
    }
    image = mp_obj_new_bytes(jpg_buf, jpg_len);
    free(jpg_buf);
  }

  esp_camera_fb_return(fb);
  return image;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(camera_jpeg_obj, 0, camera_jpeg);

/* --------------------------------------------------------------------------
 * camera.flip([enable])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_flip(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Flipping Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.vflip);
  }

  int dir = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_vflip(s, dir);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_flip_obj, 0, 1, camera_flip);

/* --------------------------------------------------------------------------
 * camera.mirror([enable])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_mirror(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Mirroring Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.hmirror);
  }

  int dir = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_hmirror(s, dir);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_mirror_obj, 0, 1, camera_mirror);

/* --------------------------------------------------------------------------
 * camera.format([format])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_format(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Image Format Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int((int)s->pixformat);
  }

  int format = mp_obj_get_int(args[0]);
  if (!is_valid_format(format)) {
    mp_raise_ValueError(MP_ERROR_TEXT("Image format is not valid"));
  }

  esp_err_t err = s->set_pixformat(s, (pixformat_t)format);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_format_obj, 0, 1, camera_format);

/* --------------------------------------------------------------------------
 * camera.framesize([size])
 * -------------------------------------------------------------------------- */
static bool framesize_to_resolution(int size, int* width, int* height) {
  if (size < 0 || size >= FRAMESIZE_INVALID) {
    return false;
  }
  *width = resolution[size].width;
  *height = resolution[size].height;
  return true;
}

static mp_obj_t camera_framesize(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Framesize Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    int width = 0, height = 0;
    (void)framesize_to_resolution((int)s->status.framesize, &width, &height);
    mp_obj_t tuple[2] = {
        mp_obj_new_int(width),
        mp_obj_new_int(height),
    };
    return mp_obj_new_tuple(2, tuple);
  }

  int size = mp_obj_get_int(args[0]);
  if (size < 0 || size >= FRAMESIZE_INVALID) {
    mp_raise_ValueError(MP_ERROR_TEXT("Image framesize is not valid"));
  }

  esp_err_t err = s->set_framesize(s, (framesize_t)size);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_framesize_obj, 0, 1, camera_framesize);

/* --------------------------------------------------------------------------
 * camera.quality([quality])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_quality(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Quality Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.quality);
  }

  int val = mp_obj_get_int(args[0]);  // 10-63 lower number means higher quality
  if (val < 0) val = 0;
  if (val > 63) val = 63;
  esp_err_t err = s->set_quality(s, val);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_quality_obj, 0, 1, camera_quality);

/* --------------------------------------------------------------------------
 * camera.contrast([contrast])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_contrast(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Contrast Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.contrast);
  }

  int val = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_contrast(s, val);  // -2,2 (default 0). 2 highcontrast
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_contrast_obj, 0, 1, camera_contrast);

/* --------------------------------------------------------------------------
 * camera.saturation([saturation])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_saturation(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Saturation Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.saturation);
  }

  int val = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_saturation(s, val);  // -2,2 (default 0). -2 grayscale
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_saturation_obj, 0, 1, camera_saturation);

/* --------------------------------------------------------------------------
 * camera.brightness([brightness])
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_brightness(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Brightness Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.brightness);
  }

  int val = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_brightness(s, val);  // -2,2 (default 0). 2 brightest
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_brightness_obj, 0, 1, camera_brightness);

/* --------------------------------------------------------------------------
 * camera.speffect([effect])
 *   0 - no effect, 1 - negative, 2 - black and white,
 *   3 - reddish,   4 - greenish, 5 - blue, 6 - retro
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_speffect(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "Special Effect Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.special_effect);
  }

  int val = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_special_effect(s, val);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_speffect_obj, 0, 1, camera_speffect);

/* --------------------------------------------------------------------------
 * camera.whitebalance([whitebalance])
 *   0 - no effect, 1 - sunny, 2 - cloudy, 3 - office, 4 - home
 * -------------------------------------------------------------------------- */
static mp_obj_t camera_whitebalance(size_t n_args, const mp_obj_t* args) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) {
    ESP_LOGE(TAG, "White Balance Failed");
    return mp_const_false;
  }

  if (n_args == 0) {
    return mp_obj_new_int(s->status.wb_mode);
  }

  int val = mp_obj_get_int(args[0]);
  esp_err_t err = s->set_wb_mode(s, val);
  return (err == ESP_OK) ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_whitebalance_obj, 0, 1, camera_whitebalance);

/* --------------------------------------------------------------------------
 * 模块全局表
 * -------------------------------------------------------------------------- */
static const mp_rom_map_elem_t camera_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_camera)},

    {MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&camera_init_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&camera_deinit_obj)},
    {MP_ROM_QSTR(MP_QSTR_snapshot), MP_ROM_PTR(&camera_snapshot_obj)},
    {MP_ROM_QSTR(MP_QSTR_jpeg), MP_ROM_PTR(&camera_jpeg_obj)},
    {MP_ROM_QSTR(MP_QSTR_flip), MP_ROM_PTR(&camera_flip_obj)},
    {MP_ROM_QSTR(MP_QSTR_mirror), MP_ROM_PTR(&camera_mirror_obj)},
    {MP_ROM_QSTR(MP_QSTR_format), MP_ROM_PTR(&camera_format_obj)},
    {MP_ROM_QSTR(MP_QSTR_framesize), MP_ROM_PTR(&camera_framesize_obj)},
    {MP_ROM_QSTR(MP_QSTR_quality), MP_ROM_PTR(&camera_quality_obj)},
    {MP_ROM_QSTR(MP_QSTR_contrast), MP_ROM_PTR(&camera_contrast_obj)},
    {MP_ROM_QSTR(MP_QSTR_saturation), MP_ROM_PTR(&camera_saturation_obj)},
    {MP_ROM_QSTR(MP_QSTR_brightness), MP_ROM_PTR(&camera_brightness_obj)},
    {MP_ROM_QSTR(MP_QSTR_speffect), MP_ROM_PTR(&camera_speffect_obj)},
    {MP_ROM_QSTR(MP_QSTR_whitebalance), MP_ROM_PTR(&camera_whitebalance_obj)},

    // Constants — Pixel format
    {MP_ROM_QSTR(MP_QSTR_RGB565), MP_ROM_INT(PIXFORMAT_RGB565)},        // 2BPP/RGB565
    {MP_ROM_QSTR(MP_QSTR_YUV422), MP_ROM_INT(PIXFORMAT_YUV422)},        // 2BPP/YUV422
    {MP_ROM_QSTR(MP_QSTR_YUV420), MP_ROM_INT(PIXFORMAT_YUV420)},        // 1.5BPP/YUV420
    {MP_ROM_QSTR(MP_QSTR_GRAYSCALE), MP_ROM_INT(PIXFORMAT_GRAYSCALE)},  // 1BPP/GRAYSCALE
    {MP_ROM_QSTR(MP_QSTR_JPEG), MP_ROM_INT(PIXFORMAT_JPEG)},            // JPEG/COMPRESSED
    {MP_ROM_QSTR(MP_QSTR_RGB888), MP_ROM_INT(PIXFORMAT_RGB888)},        // 3BPP/RGB888
    {MP_ROM_QSTR(MP_QSTR_RAW), MP_ROM_INT(PIXFORMAT_RAW)},              // RAW
    {MP_ROM_QSTR(MP_QSTR_RGB444), MP_ROM_INT(PIXFORMAT_RGB444)},        // 3BP2P/RGB444
    {MP_ROM_QSTR(MP_QSTR_RGB555), MP_ROM_INT(PIXFORMAT_RGB555)},        // 3BP2P/RGB555
    {MP_ROM_QSTR(MP_QSTR_RAW8), MP_ROM_INT(PIXFORMAT_RAW8)},            // RAW 8-bit

    // Constants — Frame size
    {MP_ROM_QSTR(MP_QSTR_FRAME_96X96), MP_ROM_INT(FRAMESIZE_96X96)},      // 96x96
    {MP_ROM_QSTR(MP_QSTR_FRAME_QQVGA), MP_ROM_INT(FRAMESIZE_QQVGA)},      // 160x120
    {MP_ROM_QSTR(MP_QSTR_FRAME_128X128), MP_ROM_INT(FRAMESIZE_128X128)},  // 128x128
    {MP_ROM_QSTR(MP_QSTR_FRAME_QCIF), MP_ROM_INT(FRAMESIZE_QCIF)},        // 176x144
    {MP_ROM_QSTR(MP_QSTR_FRAME_HQVGA), MP_ROM_INT(FRAMESIZE_HQVGA)},      // 240x176
    {MP_ROM_QSTR(MP_QSTR_FRAME_240X240), MP_ROM_INT(FRAMESIZE_240X240)},  // 240x240
    {MP_ROM_QSTR(MP_QSTR_FRAME_QVGA), MP_ROM_INT(FRAMESIZE_QVGA)},        // 320x240
    {MP_ROM_QSTR(MP_QSTR_FRAME_320X320), MP_ROM_INT(FRAMESIZE_320X320)},  // 320x320
    {MP_ROM_QSTR(MP_QSTR_FRAME_CIF), MP_ROM_INT(FRAMESIZE_CIF)},          // 400x296
    {MP_ROM_QSTR(MP_QSTR_FRAME_HVGA), MP_ROM_INT(FRAMESIZE_HVGA)},        // 480x320
    {MP_ROM_QSTR(MP_QSTR_FRAME_VGA), MP_ROM_INT(FRAMESIZE_VGA)},          // 640x480
    {MP_ROM_QSTR(MP_QSTR_FRAME_SVGA), MP_ROM_INT(FRAMESIZE_SVGA)},        // 800x600
    {MP_ROM_QSTR(MP_QSTR_FRAME_XGA), MP_ROM_INT(FRAMESIZE_XGA)},          // 1024x768
    {MP_ROM_QSTR(MP_QSTR_FRAME_HD), MP_ROM_INT(FRAMESIZE_HD)},            // 1280x720
    {MP_ROM_QSTR(MP_QSTR_FRAME_SXGA), MP_ROM_INT(FRAMESIZE_SXGA)},        // 1280x1024
    {MP_ROM_QSTR(MP_QSTR_FRAME_UXGA), MP_ROM_INT(FRAMESIZE_UXGA)},        // 1600x1200
    // 3MP Sensors
    {MP_ROM_QSTR(MP_QSTR_FRAME_FHD), MP_ROM_INT(FRAMESIZE_FHD)},      // 1920x1080
    {MP_ROM_QSTR(MP_QSTR_FRAME_P_HD), MP_ROM_INT(FRAMESIZE_P_HD)},    //  720x1280
    {MP_ROM_QSTR(MP_QSTR_FRAME_P_3MP), MP_ROM_INT(FRAMESIZE_P_3MP)},  //  864x1536
    {MP_ROM_QSTR(MP_QSTR_FRAME_QXGA), MP_ROM_INT(FRAMESIZE_QXGA)},    // 2048x1536
    // 5MP Sensors
    {MP_ROM_QSTR(MP_QSTR_FRAME_QHD), MP_ROM_INT(FRAMESIZE_QHD)},      // 2560x1440
    {MP_ROM_QSTR(MP_QSTR_FRAME_WQXGA), MP_ROM_INT(FRAMESIZE_WQXGA)},  // 2560x1600
    {MP_ROM_QSTR(MP_QSTR_FRAME_P_FHD), MP_ROM_INT(FRAMESIZE_P_FHD)},  // 1088x1920
    {MP_ROM_QSTR(MP_QSTR_FRAME_QSXGA), MP_ROM_INT(FRAMESIZE_QSXGA)},  // 2560x1920
    {MP_ROM_QSTR(MP_QSTR_FRAME_5MP), MP_ROM_INT(FRAMESIZE_5MP)},      // 2592x1944

    // Constants — White balance
    {MP_ROM_QSTR(MP_QSTR_WB_NONE), MP_ROM_INT(WB_NONE)},
    {MP_ROM_QSTR(MP_QSTR_WB_SUNNY), MP_ROM_INT(WB_SUNNY)},
    {MP_ROM_QSTR(MP_QSTR_WB_CLOUDY), MP_ROM_INT(WB_CLOUDY)},
    {MP_ROM_QSTR(MP_QSTR_WB_OFFICE), MP_ROM_INT(WB_OFFICE)},
    {MP_ROM_QSTR(MP_QSTR_WB_HOME), MP_ROM_INT(WB_HOME)},

    // Constants — Special effect
    {MP_ROM_QSTR(MP_QSTR_EFFECT_NONE), MP_ROM_INT(EFFECT_NONE)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_NEG), MP_ROM_INT(EFFECT_NEG)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_BW), MP_ROM_INT(EFFECT_BW)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_RED), MP_ROM_INT(EFFECT_RED)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_GREEN), MP_ROM_INT(EFFECT_GREEN)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_BLUE), MP_ROM_INT(EFFECT_BLUE)},
    {MP_ROM_QSTR(MP_QSTR_EFFECT_RETRO), MP_ROM_INT(EFFECT_RETRO)},

    // Constants — XCLK frequency
    {MP_ROM_QSTR(MP_QSTR_XCLK_10MHz), MP_ROM_INT(XCLK_FREQ_10MHz)},
    {MP_ROM_QSTR(MP_QSTR_XCLK_20MHz), MP_ROM_INT(XCLK_FREQ_20MHz)},

    // Constants — Frame buffer location
    {MP_ROM_QSTR(MP_QSTR_DRAM), MP_ROM_INT(CAMERA_FB_IN_DRAM)},
    {MP_ROM_QSTR(MP_QSTR_PSRAM), MP_ROM_INT(CAMERA_FB_IN_PSRAM)},
};

static MP_DEFINE_CONST_DICT(camera_module_globals, camera_module_globals_table);

const mp_obj_module_t mp_module_camera_system = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t*)&camera_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_camera, mp_module_camera_system);

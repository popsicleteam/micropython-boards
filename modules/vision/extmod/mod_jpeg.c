/*
 * JPEG module (zero-copy, DMA-aligned)
 *
 * 构造:
 *   - jpeg.Buffer(size)                -> 32B 对齐 DMA 缓冲（finalizer 自动释放）
 *   - jpeg.Image(w, h, format=RGB565)  -> image.Image，像素 32B 对齐，可复用
 *
 * decode 参数:
 *   - format    允许位置或关键字
 *   - image     仅关键字，只接受 image.Image（原地写入，返回同一个 Image）
 *   - buffer    仅关键字，只接受 jpeg.Buffer（返回新 image.Image 包装它）
 *   - image / buffer 互斥
 *
 * encode 参数:
 *   - img       image.Image，必需位置参数
 *   - quality   允许位置或关键字，1..100，默认 90
 *   - 返回      bytes（JPEG 码流，由 Python 持有）
 */

#include <string.h>

#include "esp_err.h"
#include "esp_heap_caps.h"
#include "py/mphal.h"
#include "py/objstr.h"
#include "py/runtime.h"

#ifndef CMSIS_MCU_H
#define CMSIS_MCU_H "cmsis_compiler.h"
#endif

#ifndef NO_QSTR
#include "imlib.h"
#endif

#include "jpeg.h"
#include "py_image.h"

#define JPEG_DMA_ALIGN 32

/* ================================================================= */
/* jpeg.Buffer: 32 字节对齐 DMA 内存，GC 时自动释放                   */
/* ================================================================= */

typedef struct _jpeg_buffer_obj_t {
  mp_obj_base_t base;
  uint8_t* buf;
  size_t size;
} jpeg_buffer_obj_t;

static const mp_obj_type_t jpeg_buffer_type;

static void jpeg_buffer_free(jpeg_buffer_obj_t* self) {
  if (self->buf) {
    heap_caps_free(self->buf);
    self->buf = NULL;
    self->size = 0;
  }
}

static mp_obj_t jpeg_buffer___del__(mp_obj_t self_in) {
  jpeg_buffer_free(MP_OBJ_TO_PTR(self_in));
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(jpeg_buffer___del___obj, jpeg_buffer___del__);

static mp_obj_t jpeg_buffer_release(mp_obj_t self_in) {
  jpeg_buffer_free(MP_OBJ_TO_PTR(self_in));
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(jpeg_buffer_release_obj, jpeg_buffer_release);

static mp_obj_t jpeg_buffer_size_method(mp_obj_t self_in) {
  return mp_obj_new_int_from_uint(((jpeg_buffer_obj_t*)self_in)->size);
}
static MP_DEFINE_CONST_FUN_OBJ_1(jpeg_buffer_size_obj, jpeg_buffer_size_method);

static mp_int_t jpeg_buffer_get_buffer(mp_obj_t self_in, mp_buffer_info_t* bi, mp_uint_t flags) {
  jpeg_buffer_obj_t* self = MP_OBJ_TO_PTR(self_in);
  if (!self->buf) {
    bi->buf = NULL;
    bi->len = 0;
    bi->typecode = -1;
    return 1;
  }
  bi->buf = self->buf;
  bi->len = self->size;
  bi->typecode = 'B';
  return 0;
}

static const mp_rom_map_elem_t jpeg_buffer_locals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&jpeg_buffer___del___obj)},
    {MP_ROM_QSTR(MP_QSTR_release), MP_ROM_PTR(&jpeg_buffer_release_obj)},
    {MP_ROM_QSTR(MP_QSTR_size), MP_ROM_PTR(&jpeg_buffer_size_obj)},
};
static MP_DEFINE_CONST_DICT(jpeg_buffer_locals, jpeg_buffer_locals_table);

static uint8_t* jpeg_alloc_aligned(size_t size) {
  uint8_t* p = heap_caps_aligned_alloc(JPEG_DMA_ALIGN, size, MALLOC_CAP_DMA | MALLOC_CAP_8BIT);
  if (!p) {
    p = heap_caps_aligned_alloc(JPEG_DMA_ALIGN, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  }
  return p;
}

static jpeg_buffer_obj_t* jpeg_buffer_new(size_t size) {
#if MICROPY_ENABLE_FINALISER
  jpeg_buffer_obj_t* o = mp_obj_malloc_with_finaliser(jpeg_buffer_obj_t, &jpeg_buffer_type);
#else
  jpeg_buffer_obj_t* o = m_new_obj(jpeg_buffer_obj_t);
  o->base.type = &jpeg_buffer_type;
#endif
  o->buf = NULL;
  o->size = 0;
  if (size > 0) {
    o->buf = jpeg_alloc_aligned(size);
    if (!o->buf) {
      m_del_obj(jpeg_buffer_obj_t, o);
      return NULL;
    }
    o->size = size;
  }
  return o;
}

/* jpeg.Buffer(size) */
static mp_obj_t jpeg_buffer_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args) {
  mp_arg_check_num(n_args, n_kw, 1, 1, false);
  int size = mp_obj_get_int(args[0]);
  if (size <= 0) {
    mp_raise_ValueError(MP_ERROR_TEXT("size must be > 0"));
  }
  jpeg_buffer_obj_t* o = jpeg_buffer_new((size_t)size);
  if (!o) {
    mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("no aligned memory"));
  }
  return MP_OBJ_FROM_PTR(o);
}

static MP_DEFINE_CONST_OBJ_TYPE(jpeg_buffer_type,
                                MP_QSTR_Buffer,
                                MP_TYPE_FLAG_NONE,
                                make_new,
                                jpeg_buffer_make_new,
                                buffer,
                                jpeg_buffer_get_buffer,
                                locals_dict,
                                &jpeg_buffer_locals);

/* ================================================================= */
/* jpeg.Image(w, h, format=RGB565) -> image.Image                    */
/*   工厂式类型：make_new 返回 py_image_type 实例，                     */
/*   像素 32B 对齐，生命周期由 jpeg.Buffer(finalizer) 管理。           */
/* ================================================================= */

static const mp_obj_type_t jpeg_image_type;

static mp_obj_t jpeg_image_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args) {
  enum { ARG_width, ARG_height, ARG_format };
  static const mp_arg_t allowed_args[] = {
      {MP_QSTR_width, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
      {MP_QSTR_height, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
      {MP_QSTR_format, MP_ARG_INT, {.u_int = PIXFORMAT_RGB565}},
  };
  mp_arg_val_t parsed[MP_ARRAY_SIZE(allowed_args)];
  mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed);

  int width = parsed[ARG_width].u_int;
  int height = parsed[ARG_height].u_int;
  int format = parsed[ARG_format].u_int;

  if (width <= 0 || height <= 0 || width > 4096 || height > 4096) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid width/height"));
  }
  if (format != PIXFORMAT_GRAYSCALE && format != PIXFORMAT_RGB565) {
    mp_raise_ValueError(MP_ERROR_TEXT("format must be GRAYSCALE or RGB565"));
  }

  image_t tmp = {.w = width, .h = height, .pixfmt = (pixformat_t)format};
  size_t out_size = image_size(&tmp);
  if (out_size == 0) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output size"));
  }

  jpeg_buffer_obj_t* holder = jpeg_buffer_new(out_size);
  if (!holder) {
    mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("no aligned memory"));
  }

  return esp_vision_image_new(width, height, format, holder->buf, MP_OBJ_FROM_PTR(holder));
}

static MP_DEFINE_CONST_OBJ_TYPE(jpeg_image_type, MP_QSTR_Image, MP_TYPE_FLAG_NONE, make_new, jpeg_image_make_new);

/* ================================================================= */
/* JPEG 头解析                                                        */
/* ================================================================= */

typedef struct {
  size_t start, end;
  uint16_t width, height;
  bool progressive, has_sof;
} jpeg_header_t;

static bool jpeg_parse_header(const uint8_t* buf, size_t len, jpeg_header_t* hdr) {
  memset(hdr, 0, sizeof(*hdr));
  hdr->start = hdr->end = len;

  for (size_t i = 0; i + 1 < len; i++) {
    if (buf[i] == 0xFF && buf[i + 1] == 0xD8) {
      hdr->start = i;
      break;
    }
  }
  if (hdr->start == len) return false;

  for (size_t i = hdr->start + 2; i + 1 < len; i++) {
    if (buf[i] == 0xFF && buf[i + 1] == 0xD9) {
      hdr->end = i + 2;
      break;
    }
  }
  if (hdr->end == len) return false;

  size_t i = hdr->start + 2;
  while (i + 9 < hdr->end) {
    if (buf[i] != 0xFF) {
      i++;
      continue;
    }
    uint8_t m = buf[i + 1];
    if ((m >= 0xD0 && m <= 0xD7) || m == 0xD8 || m == 0xD9) {
      i += 2;
      continue;
    }
    if (m == 0xDA) break;
    if (i + 3 >= hdr->end) break;
    size_t sl = ((size_t)buf[i + 2] << 8) | buf[i + 3];
    if (i + 2 + sl > hdr->end) break;
    if (m == 0xC0 || m == 0xC1 || m == 0xC2) {
      hdr->height = ((uint16_t)buf[i + 5] << 8) | buf[i + 6];
      hdr->width = ((uint16_t)buf[i + 7] << 8) | buf[i + 8];
      hdr->progressive = (m == 0xC2);
      hdr->has_sof = true;
      break;
    }
    i += 2 + sl;
  }
  return true;
}

static inline bool is_aligned(const void* p) {
  return ((uintptr_t)p & (JPEG_DMA_ALIGN - 1)) == 0;
}

/* ================================================================= */
/* jpeg.decode(data, width, height, format=RGB565, *,                */
/*             image=None, buffer=None)                              */
/*                                                                   */
/* image=  : Image 对象，原地写入，返回同一个 Image                  */
/* buffer= : jpeg.Buffer 对象，写入 buffer，返回新 Image 包装它      */
/* 都不传  : 内部新分配 jpeg_buffer，返回新 Image                    */
/* image / buffer 互斥                                               */
/* ================================================================= */

static mp_obj_t jpeg_decode(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args) {
  enum { ARG_data, ARG_width, ARG_height, ARG_format, ARG_image, ARG_buffer };
  static const mp_arg_t allowed_args[] = {
      {MP_QSTR_data, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE}},
      {MP_QSTR_width, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
      {MP_QSTR_height, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
      {MP_QSTR_format, MP_ARG_INT, {.u_int = PIXFORMAT_RGB565}},
      {MP_QSTR_image, MP_ARG_OBJ | MP_ARG_KW_ONLY, {.u_rom_obj = MP_ROM_NONE}},
      {MP_QSTR_buffer, MP_ARG_OBJ | MP_ARG_KW_ONLY, {.u_rom_obj = MP_ROM_NONE}},
  };
  mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
  mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

  mp_obj_t image_obj = args[ARG_image].u_obj;
  mp_obj_t buffer_obj = args[ARG_buffer].u_obj;

  if ((image_obj != mp_const_none) && (buffer_obj != mp_const_none)) {
    mp_raise_TypeError(MP_ERROR_TEXT("image= and buffer= are mutually exclusive"));
  }

  mp_buffer_info_t src;
  mp_get_buffer_raise(args[ARG_data].u_obj, &src, MP_BUFFER_READ);

  int width = args[ARG_width].u_int;
  int height = args[ARG_height].u_int;
  int format = args[ARG_format].u_int;

  if (width <= 0 || height <= 0 || width > 4096 || height > 4096) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid width/height"));
  }
  if (format != PIXFORMAT_GRAYSCALE && format != PIXFORMAT_RGB565) {
    mp_raise_ValueError(MP_ERROR_TEXT("format must be GRAYSCALE or RGB565"));
  }
  if (src.len < 128) {
    mp_raise_ValueError(MP_ERROR_TEXT("JPEG stream too short"));
  }

  jpeg_header_t hdr;
  if (!jpeg_parse_header(src.buf, src.len, &hdr)) {
    mp_raise_ValueError(MP_ERROR_TEXT("no SOI/EOI in JPEG stream"));
  }
  if (hdr.progressive) {
    mp_raise_ValueError(MP_ERROR_TEXT("progressive JPEG not supported"));
  }
  if (hdr.has_sof && (hdr.width != width || hdr.height != height)) {
    mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("JPEG is %ux%u, not %dx%d"), (unsigned)hdr.width, (unsigned)hdr.height, width, height);
  }

  const uint8_t* in_ptr = (const uint8_t*)src.buf + hdr.start;
  size_t in_len = hdr.end - hdr.start;

  image_t tmp = {.w = width, .h = height, .pixfmt = (pixformat_t)format};
  size_t out_size = image_size(&tmp);
  if (out_size == 0) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output size"));
  }

  /* --- 输出目的地选择 --- */
  uint8_t* out_ptr = NULL;
  mp_obj_t result_image = MP_OBJ_NULL;
  jpeg_buffer_obj_t* holder_to_release = NULL;

  if (image_obj != mp_const_none) {
    /* Case 1: image= 必须是 Image，原地写入 */
    if (!mp_obj_is_type(image_obj, &py_image_type)) {
      mp_raise_TypeError(
          MP_ERROR_TEXT("image must be an Image object; "
                        "use jpeg.Image()"));
    }
    image_t* bimg = (image_t*)py_image_cobj(image_obj);
    if ((bimg->w != width) || (bimg->h != height) || (bimg->pixfmt != (pixformat_t)format)) {
      mp_raise_ValueError(MP_ERROR_TEXT("image w/h/format mismatch"));
    }
    if (!is_aligned(bimg->data)) {
      mp_raise_msg(&mp_type_ValueError,
                   MP_ERROR_TEXT("image not 32-byte aligned; "
                                 "use jpeg.Image()"));
    }
    if (image_size(bimg) < out_size) {
      mp_raise_ValueError(MP_ERROR_TEXT("image too small"));
    }
    out_ptr = bimg->data;
    result_image = image_obj;
  } else if (buffer_obj != mp_const_none) {
    /* Case 2: buffer= 必须是 jpeg.Buffer，返回新 Image 包装它 */
    if (!mp_obj_is_type(buffer_obj, &jpeg_buffer_type)) {
      mp_raise_TypeError(
          MP_ERROR_TEXT("buffer must be a jpeg.Buffer; "
                        "use jpeg.Buffer(size)"));
    }
    jpeg_buffer_obj_t* h = MP_OBJ_TO_PTR(buffer_obj);
    if (!h->buf) {
      mp_raise_ValueError(MP_ERROR_TEXT("buffer already released"));
    }
    if (h->size < out_size) {
      mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("buffer too small: need %u"), (unsigned)out_size);
    }
    out_ptr = h->buf;
    result_image = esp_vision_image_new(width, height, format, out_ptr, buffer_obj);
  } else {
    /* Case 3: 内部分配 jpeg_buffer，返回新 Image */
    jpeg_buffer_obj_t* h = jpeg_buffer_new(out_size);
    if (!h) {
      mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("no aligned mem for output"));
    }
    holder_to_release = h;
    out_ptr = h->buf;
    result_image = esp_vision_image_new(width, height, format, out_ptr, MP_OBJ_FROM_PTR(h));
  }

  /* --- 输入对齐（只在需要时拷一次） --- */
  uint8_t* in_aligned = NULL;
  if (!is_aligned(in_ptr)) {
    in_aligned = jpeg_alloc_aligned(in_len);
    if (!in_aligned) {
      if (holder_to_release) {
        jpeg_buffer_free(holder_to_release);
        m_del_obj(jpeg_buffer_obj_t, holder_to_release);
      }
      mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("no aligned mem for input"));
    }
    memcpy(in_aligned, in_ptr, in_len);
    in_ptr = in_aligned;
  }

  image_t dst = {
      .w = width,
      .h = height,
      .pixfmt = (pixformat_t)format,
      .size = out_size,
      .data = out_ptr,
  };

  esp_err_t err = esp_vision_jpeg_decode(in_ptr, in_len, &dst);

  if (in_aligned) {
    heap_caps_free(in_aligned);
  }

  if (err != ESP_OK) {
    if (holder_to_release) {
      jpeg_buffer_free(holder_to_release);
      m_del_obj(jpeg_buffer_obj_t, holder_to_release);
    }
    mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("JPEG decode failed: %s"), esp_err_to_name(err));
  }

  return result_image;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(jpeg_decode_obj, 3, jpeg_decode);

/* ================================================================= */
/* jpeg.encode(img, quality=90) -> bytes                             */
/*                                                                   */
/* img     : image.Image 对象，必需位置参数                          */
/* quality : 允许位置或关键字，1..100，默认 90                       */
/* 返回    : bytes（JPEG 码流，由 Python 持有，不引用 img 内存）      */
/* ================================================================= */

static mp_obj_t jpeg_encode(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args) {
  enum { ARG_img, ARG_quality };
  static const mp_arg_t allowed_args[] = {
      {MP_QSTR_img, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE}},
      {MP_QSTR_quality, MP_ARG_INT, {.u_int = 90}},
  };
  mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
  mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

  image_t* img = (image_t*)py_image_cobj(args[ARG_img].u_obj);

  int quality = args[ARG_quality].u_int;
  if (quality < 1 || quality > 100) {
    mp_raise_ValueError(MP_ERROR_TEXT("quality must be between 1 and 100"));
  }

  uint8_t* jpeg_buf = NULL;
  size_t jpeg_size = 0;

  esp_err_t err = esp_vision_jpeg_encode(img, quality, &jpeg_buf, &jpeg_size);
  if (err != ESP_OK) {
    if (jpeg_buf) heap_caps_free(jpeg_buf);
    mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("JPEG encode failed: %s"), esp_err_to_name(err));
  }

  mp_obj_t result = mp_obj_new_bytes(jpeg_buf, jpeg_size);
  if (jpeg_buf) heap_caps_free(jpeg_buf);
  return result;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(jpeg_encode_obj, 1, jpeg_encode);

/* ================================================================= */
/* jpeg.deinit()                                                     */
/* ================================================================= */

static mp_obj_t jpeg_deinit(void) {
  esp_vision_jpeg_deinit();
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(jpeg_deinit_obj, jpeg_deinit);

/* ================================================================= */
/* 模块表                                                            */
/* ================================================================= */

static const mp_rom_map_elem_t jpeg_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_jpeg)},

    {MP_ROM_QSTR(MP_QSTR_decode), MP_ROM_PTR(&jpeg_decode_obj)},
    {MP_ROM_QSTR(MP_QSTR_encode), MP_ROM_PTR(&jpeg_encode_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&jpeg_deinit_obj)},

    {MP_ROM_QSTR(MP_QSTR_GRAYSCALE), MP_ROM_INT(PIXFORMAT_GRAYSCALE)},
    {MP_ROM_QSTR(MP_QSTR_RGB565), MP_ROM_INT(PIXFORMAT_RGB565)},

    /* 类型：直接通过 jpeg.Buffer(size) / jpeg.Image(w, h, format) 构造 */
    {MP_ROM_QSTR(MP_QSTR_Buffer), MP_ROM_PTR(&jpeg_buffer_type)},
    {MP_ROM_QSTR(MP_QSTR_Image), MP_ROM_PTR(&jpeg_image_type)},
};
static MP_DEFINE_CONST_DICT(jpeg_module_globals, jpeg_module_globals_table);

const mp_obj_module_t jpeg_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_t)&jpeg_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_jpeg, jpeg_module);

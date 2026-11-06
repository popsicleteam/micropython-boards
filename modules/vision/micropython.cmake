set(ESP_VISION_ROOT "${CMAKE_CURRENT_LIST_DIR}/esp_vision")
set(IMLIB_LIB_DIR "${ESP_VISION_ROOT}/components/imlib")

set(IMLIB_LIB_SRC
    ${IMLIB_LIB_DIR}/upstream/collections.c
    ${IMLIB_LIB_DIR}/upstream/apriltag.c
    ${IMLIB_LIB_DIR}/upstream/binary.c
    ${IMLIB_LIB_DIR}/upstream/bayer.c
    ${IMLIB_LIB_DIR}/upstream/blob.c
    ${IMLIB_LIB_DIR}/upstream/bmp.c
    ${IMLIB_LIB_DIR}/upstream/draw.c
    ${IMLIB_LIB_DIR}/upstream/edge.c
    ${IMLIB_LIB_DIR}/upstream/edl.c
    ${IMLIB_LIB_DIR}/upstream/eye.c
    ${IMLIB_LIB_DIR}/upstream/filter.c
    ${IMLIB_LIB_DIR}/upstream/fmath.c
    ${IMLIB_LIB_DIR}/upstream/font.c
    ${IMLIB_LIB_DIR}/upstream/fsort.c
    ${IMLIB_LIB_DIR}/upstream/hough.c
    ${IMLIB_LIB_DIR}/upstream/imlib.c
    ${IMLIB_LIB_DIR}/upstream/integral.c
    ${IMLIB_LIB_DIR}/upstream/jpegd.c
    ${IMLIB_LIB_DIR}/upstream/jpege.c
    ${IMLIB_LIB_DIR}/upstream/line.c
    ${IMLIB_LIB_DIR}/upstream/mathop.c
    ${IMLIB_LIB_DIR}/upstream/png.c
    ${IMLIB_LIB_DIR}/upstream/point.c
    ${IMLIB_LIB_DIR}/upstream/ppm.c
    ${IMLIB_LIB_DIR}/upstream/qrcode.c
    ${IMLIB_LIB_DIR}/upstream/rectangle.c
    ${IMLIB_LIB_DIR}/upstream/stats.c
    ${IMLIB_LIB_DIR}/upstream/template.c
    ${IMLIB_LIB_DIR}/upstream/yuv.c
    ${IMLIB_LIB_DIR}/compat/array.c
    ${IMLIB_LIB_DIR}/compat/fb_alloc.c
    ${IMLIB_LIB_DIR}/compat/file_utils.c
    ${IMLIB_LIB_DIR}/compat/framebuffer_compat.c
    ${IMLIB_LIB_DIR}/compat/lab_table.c
    ${IMLIB_LIB_DIR}/compat/sincos_table.c
    ${IMLIB_LIB_DIR}/compat/unaligned_memcpy.c
    ${IMLIB_LIB_DIR}/compat/umm_malloc.c
)

add_library(usermod_vision INTERFACE)
target_sources(usermod_vision INTERFACE
    ${IMLIB_LIB_SRC}
    ${ESP_VISION_ROOT}/modules/py_image.c
    ${ESP_VISION_ROOT}/modules/py_imageio.c
    ${ESP_VISION_ROOT}/modules/py_helper.c
    ${ESP_VISION_ROOT}/modules/py_espdl.cpp
    ${ESP_VISION_ROOT}/modules/py_tflite.cpp
    ${ESP_VISION_ROOT}/platform/ev_memory.c
    ${ESP_VISION_ROOT}/platform/jpeg.c
    ${ESP_VISION_ROOT}/platform/nanotrack.cpp
    ${CMAKE_CURRENT_LIST_DIR}/extmod/mod_jpeg.c
    ${CMAKE_CURRENT_LIST_DIR}/extmod/vision_preview_none.c
)
target_include_directories(usermod_vision INTERFACE
    ${ESP_VISION_ROOT}/modules
    ${ESP_VISION_ROOT}/platform
    ${IMLIB_LIB_DIR}/upstream
    ${IMLIB_LIB_DIR}/include
    ${CMAKE_CURRENT_LIST_DIR}/extmod
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_BINARY_DIR}
)
target_compile_definitions(usermod_vision INTERFACE CMSIS_MCU_H="cmsis_compiler.h" OMV_NO_GPL=1)
list(APPEND MICROPY_CPP_DEF_EXTRA "CMSIS_MCU_H=\"cmsis_compiler.h\"" OMV_NO_GPL=1)
target_compile_options(usermod_vision INTERFACE $<$<COMPILE_LANGUAGE:CXX>:-std=gnu++2b>)
target_link_libraries(usermod INTERFACE usermod_vision)

include(${CMAKE_CURRENT_LIST_DIR}/ulab/code/micropython.cmake)

if(NOT DEFINED ${LV_CONF_DIR})
    set(LV_CONF_DIR ${CMAKE_CURRENT_LIST_DIR})
endif()
if(NOT DEFINED ${LV_CONF_PATH})
    set(LV_CONF_PATH ${CMAKE_CURRENT_LIST_DIR}/lv_conf.h)
endif()

include(${CMAKE_CURRENT_LIST_DIR}/binding/micropython.cmake)

add_library(lvgl_fonts INTERFACE)
target_sources(lvgl_fonts INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/fonts/font_puhui_14.c
    ${CMAKE_CURRENT_LIST_DIR}/fonts/font_puhui_16.c
    ${CMAKE_CURRENT_LIST_DIR}/fonts/font_puhui_20.c
)
target_link_libraries(usermod_lvgl INTERFACE lvgl_fonts)

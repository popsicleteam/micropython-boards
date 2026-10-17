add_library(mod_camera INTERFACE)

target_sources(mod_camera INTERFACE ${CMAKE_CURRENT_LIST_DIR}/camera.c)

target_include_directories(mod_camera INTERFACE ${CMAKE_CURRENT_LIST_DIR})

target_link_libraries(usermod INTERFACE mod_camera)

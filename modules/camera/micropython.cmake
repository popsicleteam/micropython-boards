add_library(usermod_camera INTERFACE)
target_sources(usermod_camera INTERFACE ${CMAKE_CURRENT_LIST_DIR}/mod_camera.c)
target_include_directories(usermod_camera INTERFACE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(usermod INTERFACE usermod_camera)

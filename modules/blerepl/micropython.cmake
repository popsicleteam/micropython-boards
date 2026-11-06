add_library(usermod_bleuart INTERFACE)
target_sources(usermod_bleuart INTERFACE ${CMAKE_CURRENT_LIST_DIR}/mod_bleuart.c)
target_include_directories(usermod_bleuart INTERFACE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(usermod INTERFACE usermod_bleuart)

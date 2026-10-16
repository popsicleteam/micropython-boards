add_library(mod_bleuart INTERFACE)

target_sources(mod_bleuart INTERFACE ${CMAKE_CURRENT_LIST_DIR}/bleuart.c)

target_include_directories(mod_bleuart INTERFACE ${CMAKE_CURRENT_LIST_DIR})

target_link_libraries(usermod INTERFACE mod_bleuart)

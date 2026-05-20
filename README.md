# micropython-boards

编译 MicroPython 固件以支持自制开发板。

## 关于本代码库

本代码库的各级目录功能如下：

- [boards](boards/): 各种芯片主核的开发板
- [cmodules](cmodules/): C 语言编写的 MicroPython 驱动和库
- [examples](examples/): 示例代码
- [lib](lib/): 第三方库引用
- [micropython](micropython/): MicroPython 引用
- [modules](modules/): MicroPython 编写的 MicroPython 驱动和库
- [tools](tools/): 工具脚本
  - [combine](tools/combine/): 固件分区资源合并脚本
  - [fonts](tools/fonts/): 像素字转换脚本

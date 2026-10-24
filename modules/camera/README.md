# ESP-CAMERA

Fork: [https://github.com/lemariva/micropython-camera-driver](https://github.com/lemariva/micropython-camera-driver)

基于 [ESP32-CAMERA](https://github.com/espressif/esp32-camera) 的 MicroPython 版本摄像头驱动，适用于 ESP32、ESP32S2、ESP32S3 芯片，支持多款摄像头。

## 使用说明

### 基础函数

#### `camera.init(*)`

初始化摄像头，必须初始化后才能使用摄像头拍照图片。

- **关键词参数**
  - `format`, 图片数据格式

    | 格式               | 说明                  |
    | ------------------ | --------------------- |
    | `camera.RGB565`    | 2BPP/RGB565（默认值） |
    | `camera.YUV422`    | 2BPP/YUV422           |
    | `camera.YUV420`    | 1.5BPP/YUV420         |
    | `camera.GRAYSCALE` | 1BPP/灰度             |
    | `camera.JPEG`      | JPEG/压缩             |
    | `camera.RGB888`    | 3BPP/RGB888           |
    | `camera.RAW`       | RAW                   |
    | `camera.RGB444`    | 3BP2P/RGB444          |
    | `camera.RGB555`    | 3BP2P/RGB555          |
    | `camera.RAW8`      | RAW 8-bit             |

  - `framesize`, 分辨率（帧尺寸）

    | 分辨率（帧尺寸）       | 说明               |
    | ---------------------- | ------------------ |
    | `camera.FRAME_96X96`   | 96×96              |
    | `camera.FRAME_QQVGA`   | 160×120            |
    | `camera.FRAME_128X128` | 128×128            |
    | `camera.FRAME_QCIF`    | 176×144            |
    | `camera.FRAME_HQVGA`   | 240×176            |
    | `camera.FRAME_240X240` | 240×240            |
    | `camera.FRAME_QVGA`    | 320×240 （默认值） |
    | `camera.FRAME_320X320` | 320×320            |
    | `camera.FRAME_CIF`     | 400×296            |
    | `camera.FRAME_HVGA`    | 480×320            |
    | `camera.FRAME_VGA`     | 640×480            |
    | `camera.FRAME_SVGA`    | 800×600            |
    | `camera.FRAME_XGA`     | 1024×768           |
    | `camera.FRAME_HD`      | 1280×720           |
    | `camera.FRAME_SXGA`    | 1280×1024          |
    | `camera.FRAME_UXGA`    | 1600×1200          |
    | `camera.FRAME_FHD`     | 1920×1080          |
    | `camera.FRAME_P_HD`    | 720×1280           |
    | `camera.FRAME_P_3MP`   | 864×1536           |
    | `camera.FRAME_QXGA`    | 2048×1536          |
    | `camera.FRAME_QHD`     | 2560×1440          |
    | `camera.FRAME_WQXGA`   | 2560×1600          |
    | `camera.FRAME_P_FHD`   | 1088×1920          |
    | `camera.FRAME_QSXGA`   | 2560×1920          |
    | `camera.FRAME_5MP`     | 2592×1944          |

  - `quality`，JPEG 质量，默认值：12，可选范围：0~63
  - `d0`，D0 引脚
  - `d1`，D1 引脚
  - `d2`，D2 引脚
  - `d3`，D3 引脚
  - `d4`，D4 引脚
  - `d5`，D5 引脚
  - `d6`，D6 引脚
  - `d7`，D7 引脚
  - `vsync`，VSYNC 引脚
  - `href`，HREF 引脚
  - `pclk`，PCLK 引脚
  - `pwdn`，POWER 引脚
  - `reset`，RESET 引脚
  - `xclk`，XCLK 引脚
  - `sda`，SDA 引脚
  - `scl`，SCL 引脚
  - `xclk_freq`，XCLK 信号频率，默认值：`camera.XCLK_20MHz`，可选值：`camera.XCLK_10MHz`
  - `fb_count`，帧缓存数量，默认值：2
  - `fb_location`，帧缓存区，默认值：`camera.FB_PSRAM`，可选值：`camera.FB_DRAM`

#### `camera.deinit()`

卸载摄像头，释放使用的硬件资源。

#### `camera.snapshot()`

获取 1 帧图片数据。

#### `camera.jpeg(quality)`

拍摄 1 帧 JPEG 图片数据，可选设置 JPEG 质量，可选范围：0~63（低质量）。

### 查询与设置函数

以下函数都支持**“查询”**与**“设置”**两种用法：

- **不带参数**：返回当前值（查询）。
- **带参数**：设置新值，成功返回 `True`，失败返回 `False`。

#### `camera.framesize([size])`

设置或查询分辨率。

- **无参数**：返回当前分辨率的元组 `(width, height)`，例如 `(640, 480)`；若当前分辨率无法识别，返回 `(0, 0)`。
- **带参数**：设置分辨率，参数取值见上表 `camera.FRAME_*`。

```python
w, h = camera.framesize()           # 查询：例如 (640, 480)
camera.framesize(camera.FRAME_VGA)  # 设置
```

#### `camera.format([format])`

设置或查询像素格式。

- **无参数**：返回当前 `PIXFORMAT_*` 整数值（`0~9`），可直接与 `camera.JPEG`、`camera.RGB565` 等常量比较。
- **带参数**：设置像素格式，支持全部 10 种格式，取值见 `camera.init()` 的 `format` 表；超出范围抛 `ValueError`。

```python
fmt = camera.format()        # 查询：例如 camera.JPEG 的值（4）
camera.format(camera.JPEG)   # 设置
camera.format(camera.RGB565) # 设置
```

> 部分格式（`YUV420 / RAW / RAW8 / RGB444 / RGB555`）在特定传感器或 ESP32 型号上可能不受支持，此时 `set_pixformat` 失败，函数返回 `False`。

#### `camera.quality([quality])`

设置或查询 JPEG 质量。

- **无参数**：返回当前质量值，范围 `0~63`（数值越小画质越高）。
- **带参数**：设置质量，超出范围会被自动裁剪到 `0~63`。

#### `camera.flip([enable])`

设置或查询画面上下颠倒。

- **无参数**：返回当前状态，`0`（关闭）或 `1`（开启）。
- **带参数**：`0` 关闭，`1` 开启。

#### `camera.mirror([enable])`

设置或查询画面左右镜像。

- **无参数**：返回当前状态，`0`（关闭）或 `1`（开启）。
- **带参数**：`0` 关闭，`1` 开启。

#### `camera.contrast([contrast])`

设置或查询画面对比度。

- **无参数**：返回当前对比度，范围 `-2~2`。
- **带参数**：设置对比度，默认值 `0`，范围 `-2~2`（`2` 为高对比度）。

#### `camera.saturation([saturation])`

设置或查询画面饱和度。

- **无参数**：返回当前饱和度，范围 `-2~2`。
- **带参数**：设置饱和度，默认值 `0`，范围 `-2（灰度）~2`。

#### `camera.brightness([brightness])`

设置或查询画面亮度。

- **无参数**：返回当前亮度，范围 `-2~2`。
- **带参数**：设置亮度，默认值 `0`，范围 `-2~2`（`2` 为高亮度）。

#### `camera.speffect([effect])`

设置或查询画面特效。

- **无参数**：返回当前特效值，范围 `0~6`。
- **带参数**：设置特效，取值见下表；超出 `0~6` 的值会被驱动拒绝或忽略。

| 值  | 宏名                  | 说明           |
| --- | --------------------- | -------------- |
| 0   | `camera.EFFECT_NONE`  | 原图（默认值） |
| 1   | `camera.EFFECT_NEG`   | 负片           |
| 2   | `camera.EFFECT_BW`    | 黑白           |
| 3   | `camera.EFFECT_RED`   | 偏红           |
| 4   | `camera.EFFECT_GREEN` | 偏绿           |
| 5   | `camera.EFFECT_BLUE`  | 偏蓝           |
| 6   | `camera.EFFECT_RETRO` | 复古           |

#### `camera.whitebalance([whitebalance])`

设置或查询画面白平衡。

- **无参数**：返回当前白平衡模式，范围 `0~4`。
- **带参数**：设置白平衡，取值见下表。

| 值  | 宏名               | 说明           |
| --- | ------------------ | -------------- |
| 0   | `camera.WB_NONE`   | 原始（默认值） |
| 1   | `camera.WB_SUNNY`  | 晴天           |
| 2   | `camera.WB_CLOUDY` | 阴天           |
| 3   | `camera.WB_OFFICE` | 办公室         |
| 4   | `camera.WB_HOME`   | 家中           |

### 查询/设置速查表

| 函数                    | 无参返回                          | 带参返回       |
| ----------------------- | --------------------------------- | -------------- |
| `camera.framesize()`    | `(width, height)`，未知则 `(0,0)` | `True`/`False` |
| `camera.format()`       | 当前 `PIXFORMAT_*` 整数（0~9）    | `True`/`False` |
| `camera.quality()`      | `0~63`                            | `True`/`False` |
| `camera.flip()`         | `0` 或 `1`                        | `True`/`False` |
| `camera.mirror()`       | `0` 或 `1`                        | `True`/`False` |
| `camera.contrast()`     | `-2~2`                            | `True`/`False` |
| `camera.saturation()`   | `-2~2`                            | `True`/`False` |
| `camera.brightness()`   | `-2~2`                            | `True`/`False` |
| `camera.speffect()`     | `0~6`                             | `True`/`False` |
| `camera.whitebalance()` | `0~4`                             | `True`/`False` |

### 示例

```python
import camera

camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QVGA)

# 查询当前配置
print("framesize:", camera.framesize())    # (320, 240)
print("format   :", camera.format())       # 例如 4（camera.JPEG）
print("quality  :", camera.quality())      # 例如 12
print("flip     :", camera.flip())         # 0
print("mirror   :", camera.mirror())       # 0
print("contrast :", camera.contrast())     # 0
print("bright   :", camera.brightness())   # 0
print("saturate :", camera.saturation())   # 0
print("effect   :", camera.speffect())     # 0
print("wb       :", camera.whitebalance()) # 0

# 调整画面
camera.flip(1)
camera.mirror(1)
camera.contrast(1)
camera.brightness(1)
camera.speffect(camera.EFFECT_GRAYSCALE)   # 黑白
camera.whitebalance(camera.WB_SUNNY)       # 晴天
camera.quality(10)

# 再次确认
print(camera.flip(), camera.mirror(), camera.contrast())
print(camera.speffect(), camera.whitebalance(), camera.quality())

# 切换像素格式
camera.format(camera.RGB565)
print("new format:", camera.format())      # 0

camera.deinit()
```

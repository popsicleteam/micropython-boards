# `Servo` - 舵机控制

Fork: [https://github.com/redoxcode/micropython-servo.git](https://github.com/redoxcode/micropython-servo.git)

## 使用说明

### 基础函数

#### `Servo(*)`

使用以下参数构造并返回一个新的 `Servo` 对象：

- `pin`, 连接舵机的引脚，`Pin` 对象
- `min_us`, 最小脉冲宽度（单位：us），默认 544
- `max_us`, 最大脉冲宽度（单位：us），默认 2400
- `min_deg`, 最小舵机角度（单位：度），默认 0
- `max_deg`, 最大舵机角度（单位：度），默认 180
- `freq`, PWM 周期的频率（单位：Hz），默认 50

#### `servo.init(pin, min_us, max_us, min_deg, max_deg)`

初始化 Servo，参数同构造函数。

#### `servo.deinit()`

反初始化 `Servo`，释放引脚资源。

#### `servo.write(deg)`

将舵机转到指定的角度，`deg` 角度范围必须在初始参数的最小舵机角度到最大舵机角度之间。

#### `servo.read()

返回舵机最后转到的角度（非当前实时角度）。

#### `servo.write_rad(rad)

将舵机转到指定的弧度，`rad` 弧度值。

#### `servo.read_rad()

返回舵机最后转到的弧度（非当前实时弧度）。

#### `servo.write_us(us)

将舵机转到指定脉冲宽度（单位：us）所对应的角度位置，`us` 有效值范围必须在初始参数的最小脉冲宽度到最大脉冲宽度之间。

#### `servo.read_us()

返回舵机最后的脉冲宽度（单位：us，非当前实时脉冲宽度）。

#### `servo.off()

关闭舵机，停止工作。

### 扩展函数

#### `Servo90(pin, *)`

使用以下参数构造并返回一个最大角度90°的 `Servo90` 对象，其余参数与 `Servo` 参数项相同，默认值对应 Geekservo 90°舵机参数：

- `pin`, 连接舵机的引脚，Pin 对象

#### `Servo180(pin, *)`

使用以下参数构造并返回一个最大角度180°的 `Servo180` 对象，其余参数与 `Servo` 参数项相同，默认值对应 Geekservo 180°舵机参数：

- `pin`, 连接舵机的引脚，Pin 对象

#### `Servo270(pin, *)`

使用以下参数构造并返回一个最大角度270°的 `Servo270` 对象，其余参数与 `Servo` 参数项相同，默认值对应 Geekservo 270°舵机参数：

- `pin`, 连接舵机的引脚，Pin 对象

#### `Servo360(pin, *)`

使用以下参数构造并返回一个最大角度360°的 `Servo360` 对象，其余参数与 `Servo` 参数项相同，默认值对应 Geekservo 360°（区间）舵机参数：

- `pin`, 连接舵机的引脚，Pin 对象

#### `Servo360Motor(*)`

使用以下参数构造并返回一个360°连续转动的 `Servo360Motor` 对象，其余参数与 `Servo` 参数项相同，默认值对应 Geekservo 360°（连续旋转）电机参数：

- `pin`, 连接舵机的引脚，Pin 对象

#### `motor.run(back)`

开始电机转动（正转），`back` 是否反向转动，默认 False

#### `motor.stop()`

停止电机转动。

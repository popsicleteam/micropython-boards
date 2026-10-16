"""
jsonnvs.py

用途：
    纯 MicroPython 实现的 NVS 兼容库。接口与 ``esp32.NVS`` 一致，
    用于 NVS 不可用的平台（PC、非 ESP32 芯片、无 NVS 分区的固件）。

目标固件：
    MicroPython v1.18+（在 ESP32 / v1.20 上验证）。

依赖：
    os / json / binascii / micropython。
    均为 MicroPython 固件内置模块，无需额外安装。

存储格式：
    每个 namespace 一个 JSON 文件，文件放在 ``<path>/<namespace>.json``。
    ``path`` 默认 ``/nvs``；可通过构造参数覆盖。
    文件内容::

        { "counter": ["i32", 42], "name": ["blob", "<base64>"] }

    每个值存成 ``[类型标签, 数据]``，读回时恢复原始类型。
    blob 使用 base64 编码。

使用示例::

    from jsonnvs import NVS

    # 默认路径 /nvs/wifi.json
    nvs = NVS("wifi")

    # 自定义目录 /flash/cfg/wifi.json
    nvs2 = NVS("wifi", path="/flash/cfg")

    nvs.set_i32("channel", 6)
    nvs.set_blob("ssid", b"MyAP")
    nvs.commit()

    print(nvs.get_i32("channel"))   # 6
    print(nvs.get_str("ssid"))      # MyAP

    # 边界：不落盘
    nvs.set_i32("tmp", 1)
    # ... 未 commit，断电即丢

    # 异常处理
    try:
        nvs.get_i32("nonexistent")
    except OSError as exc:
        print("key missing:", exc)
"""

import binascii
import json
import os

from micropython import const

__all__ = ("NVS",)

# --- 模块级常量（const 包装，编译期折叠） --------------------------------
_TAG_I32 = const("i32")
_TAG_BLOB = const("blob")

_SUFFIX_JSON = const(".json")
_SUFFIX_TMP = const(".tmp")

_DEFAULT_DIR = const("/nvs")
_PATH_SEP = const("/")

_DEFAULT_BLOB_SIZE = const(1024)
_UTF8 = const("utf-8")

_ERR_NO_KEY = const("NVS key not found: %s")
_ERR_BAD_BLOB = const("corrupted blob for key: %s")
_ERR_BUF_SMALL = const("blob exceeds buffer size for key: %s")
_ERR_NS_INVALID = const("namespace must be a non-empty str")
_ERR_DEINIT = const("NVS instance is deinitialized")


class NVS:
    """用 JSON 文件实现的 NVS，接口仿 ``esp32.NVS``。

    不变量：
        - ``_path`` 在实例生命周期内不变。
        - ``_data`` 始终为 dict；文件损坏时降级为空 dict。
        - ``deinit()`` 之后所有公开方法抛 ``RuntimeError``。

    参数：
        namespace (str): 非空字符串，作为文件名主体（不含 ``.json``）。
        path (str | None): 存放文件的目录，默认 ``"/nvs"``。
            实际读写路径为 ``<path>/<namespace>.json``。
            构造时会尝试创建该目录（若不存在）。

    典型用法::

        nvs = NVS("app")                 # /nvs/app.json
        nvs = NVS("app", path="/flash")  # /flash/app.json
        nvs.set_i32("boot_count", 42, commit=True)
        print(nvs.get_i32("boot_count"))
        nvs.deinit()
    """

    __slots__ = ("_ns", "_path", "_data", "_deinited")

    def __init__(self, namespace, path=None):
        """
        Args:
            namespace (str): 非空字符串。
            path (str | None): 存放目录，默认 ``"/nvs"``。

        Raises:
            ValueError: namespace 不是非空字符串。
        """
        if not isinstance(namespace, str) or not namespace:
            raise ValueError(_ERR_NS_INVALID)
        self._ns = namespace

        if path is None:
            path = _DEFAULT_DIR
        # 去掉尾部斜杠，便于统一拼接
        if path.endswith(_PATH_SEP):
            path = path[: -len(_PATH_SEP)]
        self._ensure_dir(path)

        if namespace.endswith(_SUFFIX_JSON):
            filename = namespace
        else:
            filename = namespace + _SUFFIX_JSON
        self._path = path + _PATH_SEP + filename

        self._data = {}
        self._deinited = False
        self._load()

    # -- 内部工具 -------------------------------------------------------
    @staticmethod
    def _ensure_dir(path):
        """确保目录存在；失败时静默忽略，由后续文件操作报错。"""
        if not path:
            return
        try:
            os.mkdir(path)
        except OSError:
            # 目录已存在，或父目录不存在——后者会在 open() 时暴露
            pass

    def _check_alive(self):
        if self._deinited:
            raise RuntimeError(_ERR_DEINIT)

    def _read(self):
        """从磁盘读 JSON。

        降级说明（有意为之）：
            - 文件不存在：正常的首次使用，返回 ``{}``。
            - JSON 解析失败（文件损坏）：返回 ``{}``，静默丢弃损坏内容。
              若调用方需要感知损坏，请自行捕获 OSError 并直接读取文件。
        """
        try:
            with open(self._path, "r") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except OSError:
            # 文件不存在：首次使用，正常路径
            return {}
        except ValueError:
            # 文件损坏：降级为空数据（见 docstring 说明）
            return {}

    def _load(self):
        self._data = self._read()

    def _save(self):
        """原子写：先写 .tmp，再 os.rename。

        使用 tmp+rename 的原因：掉电时原文件不会被半写状态覆盖。
        """
        tmp_path = self._path + _SUFFIX_TMP
        with open(tmp_path, "w") as handle:
            json.dump(self._data, handle)
        try:
            os.remove(self._path)
        except OSError:
            # 原文件不存在：首次写入，正常路径
            pass
        os.rename(tmp_path, self._path)

    def _entry(self, key, tag):
        entry = self._data.get(key)
        if entry is None or entry[0] != tag:
            raise OSError(_ERR_NO_KEY % key)
        return entry[1]

    # -- 生命周期 -------------------------------------------------------
    def deinit(self):
        """释放本实例持有的内存。

        幂等：重复调用无副作用。
        注意：
            - 未 commit 的改动会被丢弃。
            - 磁盘上已保存的 JSON 文件不受影响。
        之后调用任何其它方法均抛 ``RuntimeError``。
        """
        self._data = None
        self._deinited = True

    # -- 公共 API（与 esp32.NVS 对齐） ----------------------------------
    def commit(self):
        """把内存中的改动落盘。

        Raises:
            RuntimeError: 已 deinit。
            OSError: 文件写入失败。
        """
        self._check_alive()
        self._save()

    def erase_key(self, key):
        """删除一个 key。需要 ``commit()`` 才落盘。

        Args:
            key (str): 键名。
        Raises:
            RuntimeError: 已 deinit。
        """
        self._check_alive()
        if key in self._data:
            del self._data[key]

    # -- i32 ------------------------------------------------------------
    def get_i32(self, key):
        """读取 32 位整数。

        Args:
            key (str): 键名。
        Returns:
            int: 值。
        Raises:
            OSError: key 不存在或类型不匹配。
            RuntimeError: 已 deinit。
        """
        self._check_alive()
        return int(self._entry(key, _TAG_I32))

    def set_i32(self, key, value):
        """写入 32 位整数（不落盘，需 commit）。

        Args:
            key (str): 键名。
            value (int): 值。
        Raises:
            RuntimeError: 已 deinit。
        """
        self._check_alive()
        self._data[key] = [_TAG_I32, int(value)]

    # -- blob -----------------------------------------------------------
    def get_blob(self, key, buf):
        """读 blob 到 ``buf``。

        Args:
            key (str): 键名。
            buf (bytearray): 输出缓冲，必须足够大。
        Returns:
            int: 实际写入字节数。
        Raises:
            OSError: key 不存在、base64 损坏、或 buf 太小。
            RuntimeError: 已 deinit。
        """
        self._check_alive()
        encoded = self._entry(key, _TAG_BLOB)
        try:
            raw = binascii.a2b_base64(encoded)
        except (ValueError, TypeError):
            raise OSError(_ERR_BAD_BLOB % key)
        if len(buf) < len(raw):
            raise OSError(_ERR_BUF_SMALL % key)
        buf[: len(raw)] = raw
        return len(raw)

    def set_blob(self, key, value):
        """写入 blob（不落盘，需 commit）。

        Args:
            key (str): 键名。
            value (bytes | bytearray | str): 值；str 按 UTF-8 编码。
        Raises:
            RuntimeError: 已 deinit。
        """
        self._check_alive()
        if isinstance(value, str):
            value = value.encode()
        encoded = binascii.b2a_base64(bytes(value)).strip()
        if isinstance(encoded, bytes):
            encoded = encoded.decode()
        self._data[key] = [_TAG_BLOB, encoded]

    # -- str（NVS 本身没有，为兼容 Settings 提供） ----------------------
    def get_str(self, key, decode=_UTF8, size=_DEFAULT_BLOB_SIZE):
        """读取 UTF-8 字符串。

        Args:
            key (str): 键名。
            decode (str): 文本编码，默认 "utf-8"。
            size (int): 内部缓冲区大小（字节），默认 1024。
        Returns:
            str: 解码后的字符串。
        """
        self._check_alive()
        buf = bytearray(size)
        n = self.get_blob(key, buf)
        return buf[:n].decode(decode)

    def set_str(self, key, value, commit=False):
        """写入字符串。

        Args:
            key (str): 键名。
            value (str | bytes): 值。
            commit (bool): 是否立即落盘，默认 False。
        """
        self._check_alive()
        if isinstance(value, str):
            value = value.encode()
        self.set_blob(key, value)
        if commit:
            self.commit()

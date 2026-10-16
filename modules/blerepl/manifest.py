c_module(".")

package(
    "blerepl",
    (
        "__init__.py",
        "ble_advertising.py",
        "bleuart_peripheral.py",
    ),
    base_path="..",
    opt=3,
)

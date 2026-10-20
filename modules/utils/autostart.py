import gc
import os


def autostart(module="example"):
    try:
        os.stat("main.py")
    except OSError:
        with open("main.py", "w") as f:
            f.write(f"import {module}\n")
        gc.collect()

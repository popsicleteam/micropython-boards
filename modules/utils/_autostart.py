import gc
import os


def autostart(prog):
    try:
        os.stat("main.py")
    except OSError:
        with open("main.py", "w") as f:
            f.write(f"import {prog}\n")
        gc.collect()

"""
Various debug reporting functions
"""
DEBUG = True

def info(msg):
    print(f"[INFO] {msg}")

def debug(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

def warn(msg, error = False):
    header = "[ERROR]" if error else "[WARNING]"
    print(f"{header} {msg}")


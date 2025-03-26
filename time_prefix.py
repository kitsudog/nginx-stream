import sys
from datetime import datetime


def add_timestamp_to_stdin():
    for line in sys.stdin:
        # 获取当前时间作为时间戳
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S') + f".{now.microsecond // 1000:03d}"
        # 输出时间戳和行内容
        print(f"[{timestamp}] {line.strip()}")


if __name__ == "__main__":
    add_timestamp_to_stdin()

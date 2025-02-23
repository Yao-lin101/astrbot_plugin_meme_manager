import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from pathlib import Path
from tests.test_sync import run_tests


def main():
    memes_dir = Path("memes")
    if not memes_dir.exists():
        print(f"错误: 目录 {memes_dir} 不存在")
        return 1

    print("\n=== 开始同步测试 ===")
    run_tests()

    return 0


if __name__ == "__main__":
    exit(main())

"""python -m web_bridge.manage 创建本地账号（交互式输入密码，或 --password-env 走环境变量）。"""

import argparse
import getpass
import os
from pathlib import Path

from web_bridge.security import Accounts


def main():
    parser = argparse.ArgumentParser(description="创建工作台账号")
    parser.add_argument("username")
    parser.add_argument("--admin", action="store_true")
    parser.add_argument(
        "--password-env",
        metavar="VAR",
        help="从指定环境变量读取密码（非交互，供云平台启动命令使用）",
    )
    args = parser.parse_args()
    if args.password_env:
        password = os.environ.get(args.password_env, "")
        if not password:
            raise SystemExit(f"环境变量 {args.password_env} 未设置")
    else:
        password = getpass.getpass("密码（至少12字符）：")
        if password != getpass.getpass("再次输入密码："):
            raise SystemExit("两次密码不同")
    directory = Path(os.environ.get("HYSYS_WEB_DATA", "var/web"))
    Accounts(directory / "accounts.sqlite3").create_user(
        args.username, password, "admin" if args.admin else "user"
    )
    print("账号已创建")


if __name__ == "__main__":
    main()

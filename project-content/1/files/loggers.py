import os
from datetime import datetime


def print_info(string: str) -> None:
    print(f"[INFO]\t\t- {string}")


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def print_error(string: str) -> None:
    print(f"[ERROR]\t\t- {timestamp()} - {string}")


def print_update(string: str) -> None:
    print(f"[UPDATE]\t- {timestamp()} - {string}")


def file_write(file: int, string: str) -> None:
    string = string + "\n"
    byte = string.encode("utf-8")
    os.write(file, byte)


def write_warning(file: int, string: str) -> None:
    file_write(file, f"[WARNING]\t- {string}")


def write_info(file: int, string: str) -> None:
    file_write(file, f"[INFO]\t\t- {string}")


def write_debug(file: int, string: str) -> None:
    file_write(file, f"[DEBUG]\t\t- {string}")
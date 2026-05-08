#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件操作工具模块
"""

import os
import traceback
from datetime import datetime
from typing import List, Optional
import pandas as pd
import questionary

# 记录生成的文件，用于出错时清理
generated_files = []


def log_error(message: str, exception: Exception = None):
    """记录错误日志到主程序目录，文件名为 ErrorLog_时间戳.log"""
    timestamp = datetime.now().strftime("%Y_%m_%d %H_%M_%S")
    log_name = f"ErrorLog_{timestamp}.log"
    with open(log_name, "w", encoding="utf-8") as f:
        f.write(f"错误发生时间: {datetime.now()}\n")
        f.write(f"错误描述: {message}\n")
        if exception:
            f.write(f"异常信息: {str(exception)}\n")
            f.write("完整堆栈:\n")
            f.write(traceback.format_exc())
    print(f"错误日志已生成: {log_name}")


def clean_generated_files():
    """删除所有已生成的过程文件"""
    global generated_files
    for path in generated_files:
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"已清理文件: {path}")
        except Exception as e:
            print(f"清理文件失败 {path}: {e}")
    generated_files.clear()


def choose_file_from_dir(directory: str, extension: str = ".txt") -> Optional[str]:
    """从文件夹中选择指定扩展名的文件，若没有返回 None"""
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
        return None
    files = [f for f in os.listdir(directory) if f.endswith(extension)]
    if not files:
        return None
    selected = questionary.select(f"请选择 {extension} 文件：", choices=files).ask()
    if selected is None:
        return None
    return os.path.join(directory, selected)


def auto_rename_path(save_path: str) -> str:
    """若文件已存在，生成带编号的新文件名"""
    if not os.path.exists(save_path):
        return save_path
    base, ext = os.path.splitext(save_path)
    counter = 1
    while True:
        new_path = f"{base}-{counter}{ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def save_excel(df: pd.DataFrame, path: str, config: dict):
    """保存 DataFrame 到 Excel，根据配置决定覆盖或重命名"""
    if not config.get("overwrite_output", False):
        path = auto_rename_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    print(f"结果已保存至：{path}")
    generated_files.append(path)
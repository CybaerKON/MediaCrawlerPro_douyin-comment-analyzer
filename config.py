#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块（含交互式向导，自动获取模型列表）
"""

import os
import json
import requests
import questionary

DEFAULT_CONFIG = {
    "mysql_host": "localhost",
    "mysql_port": 3306,
    "mysql_user": "root",
    "mysql_password": "root",
    "input_dir": "./Input",
    "output_dir": "./Output",
    "harassment_method": "keyword",
    "llm_api_key": "",
    "llm_base_url": "https://api.deepseek.com",
    "llm_model": "deepseek-v4-pro",
    "llm_prompt": (
        "你是一个极度严格的评论审核助手。请判断以下评论是否包含"
        "邀请处对象（如“处吗”“谈吗”“CPDD”“小姐姐加个微信”“185小帅”“有没有对象”等）、"
        "性暗示（如“约吗”“多少钱”等）、过度亲昵（如“宝宝”“亲亲”“抱抱”等）、"
        "骚扰性言论（如“看下私信”“妈妈”“想让你怀孕”“肥猪”“可飞”“我是他男朋友”“开你”等）"
        "或其他类似骚扰内容。\n"
        "只要评论中出现上述任意一类词语或相似表达，不论语境如何，都必须回答“是”。\n"
        "如果完全没有上述内容，才能回答“否”。\n"
        "请只回答一个汉字，不要加任何标点或说明。"
    ),
    "llm_thinking_enabled": True,
    "overwrite_output": False,
    "last_database": None,
    "last_table": None
}

CONFIG_FILE = "config.json"


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            if k not in config:
                config[k] = v
        return config
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"配置已保存至 {CONFIG_FILE}")


def _fetch_models(base_url: str, api_key: str) -> list:
    """从 OpenAI 兼容的 /v1/models 接口获取模型 ID 列表"""
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(f"{base_url.rstrip('/')}/v1/models", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["id"] for m in data.get("data", [])]
            models.sort()
            return models
        else:
            print(f"获取模型列表失败，状态码 {resp.status_code}")
            return []
    except Exception as e:
        print(f"获取模型列表异常：{e}")
        return []


def _select_model_interactive(models: list, current_model: str) -> str:
    """
    交互式选择模型：展示全部可用模型列表，用户可用方向键选择，也可输入部分名称过滤。
    """
    if not models:
        return questionary.text("未获取到模型列表，请手动输入模型名称：", default=current_model).ask()

    print("您可以使用方向键选择模型，或输入部分名称过滤列表。")
    filter_text = ""
    while True:
        filtered = [m for m in models if filter_text.lower() in m.lower()] if filter_text else models
        if not filtered:
            print(f"没有匹配 '{filter_text}' 的模型。")
            filter_text = questionary.text("输入过滤词（直接回车显示全部）：").ask() or ""
            continue

        # 构建选择列表，包含手动输入选项和所有过滤后的模型
        choices = ["（手动输入模型名称）"] + filtered
        default_choice = current_model if current_model in filtered else filtered[0]
        selected = questionary.select(
            f"请选择模型（匹配 {len(filtered)} 个）：",
            choices=choices,
            default=default_choice
        ).ask()

        if selected == "（手动输入模型名称）":
            return questionary.text("请输入模型名称：", default=current_model).ask()
        elif selected is not None:
            return selected
        else:
            # 用户取消选择，可重新输入过滤词
            filter_text = questionary.text("输入过滤词以筛选（回车显示全部）：").ask() or ""


def setup_wizard(existing_config: dict) -> dict:
    config = existing_config.copy()
    print("=== MySQL 连接配置 ===")
    config["mysql_host"] = questionary.text("主机地址：", default=config.get("mysql_host", "localhost")).ask()
    port_str = questionary.text("端口：", default=str(config.get("mysql_port", 3306))).ask()
    try:
        config["mysql_port"] = int(port_str)
    except ValueError:
        config["mysql_port"] = 3306
    config["mysql_user"] = questionary.text("用户名：", default=config.get("mysql_user", "root")).ask()
    config["mysql_password"] = questionary.password("密码：", default=config.get("mysql_password", "root")).ask()

    print("\n=== 文件路径配置 ===")
    config["input_dir"] = questionary.path("输入文件夹：", default=config.get("input_dir", "./Input")).ask()
    config["output_dir"] = questionary.path("输出文件夹：", default=config.get("output_dir", "./Output")).ask()

    print("\n=== 骚扰检测方法 ===")
    method_display = [
        "仅关键词匹配",
        "仅大语言模型（需要 API Key）",
        "两者结合（先关键词，再大模型）"
    ]
    method_map = {
        "仅关键词匹配": "keyword",
        "仅大语言模型（需要 API Key）": "llm",
        "两者结合（先关键词，再大模型）": "both"
    }
    current_method = config.get("harassment_method", "keyword")
    default_display = "仅关键词匹配"
    for d, v in method_map.items():
        if v == current_method:
            default_display = d
            break
    selected_display = questionary.select(
        "选择默认检测方法：",
        choices=method_display,
        default=default_display
    ).ask()
    config["harassment_method"] = method_map[selected_display]

    print("\n=== 大模型 API 配置 ===")
    config["llm_base_url"] = questionary.text(
        "Base URL：",
        default=config.get("llm_base_url", "https://api.deepseek.com")
    ).ask()
    config["llm_api_key"] = questionary.password("API Key：", default=config.get("llm_api_key", "")).ask()

    # 自动获取模型列表并交互选择
    if config["llm_api_key"]:
        print("正在获取可用模型列表...")
        models = _fetch_models(config["llm_base_url"], config["llm_api_key"])
        if models:
            print(f"共获取到 {len(models)} 个模型")
        config["llm_model"] = _select_model_interactive(models, config.get("llm_model", ""))
    else:
        config["llm_model"] = questionary.text("模型名称：", default=config.get("llm_model", "deepseek-v4-pro")).ask()

    config["llm_prompt"] = questionary.text(
        "提示词（用于判断骚扰内容）：",
        default=config.get("llm_prompt", DEFAULT_CONFIG["llm_prompt"])
    ).ask()

    thinking_default = config.get("llm_thinking_enabled", True)
    config["llm_thinking_enabled"] = questionary.confirm(
        "是否开启思考模式（适用于 DeepSeek v4-pro 等，开启会显示推理过程）？",
        default=thinking_default
    ).ask()

    print("\n=== 输出文件设置 ===")
    overwrite = questionary.confirm(
        "是否覆盖同名输出文件？选择【否】将自动重命名（添加 -1, -2...）",
        default=config.get("overwrite_output", False)
    ).ask()
    config["overwrite_output"] = overwrite

    config["last_database"] = None
    config["last_table"] = None
    return config
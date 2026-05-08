#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
骚扰检测模块统一入口
"""

import pandas as pd
from detection.keyword import KeywordDetector
from detection.llm import LLMDetector
from file_utils import choose_file_from_dir


def detect_harassment_with_backup(df: pd.DataFrame, config: dict, primary_method: str) -> pd.DataFrame:
    """
    根据首选方法进行检测，失败时自动回退。
    返回 DataFrame 包含列：is_harassment, llm_response, llm_reasoning
    """
    if primary_method == "keyword":
        order = ["keyword", "llm"]
    elif primary_method == "llm":
        order = ["llm", "keyword"]
    elif primary_method == "both":
        order = ["both", "llm"]
    else:
        raise ValueError(f"未知方法: {primary_method}")

    errors = []
    for method in order:
        try:
            if method == "keyword":
                keyword_file = choose_file_from_dir(config["input_dir"], ".txt")
                if not keyword_file:
                    raise FileNotFoundError("目录下不存在字典文件")
                detector = KeywordDetector(keyword_file)
                print("使用关键词匹配进行骚扰检测...")
                is_harass = df["content"].apply(
                    lambda x: detector.is_harassment(str(x)) if pd.notna(x) else False
                )
                result_df = pd.DataFrame({
                    "is_harassment": is_harass,
                    "llm_response": "",
                    "llm_reasoning": ""
                }, index=df.index)
                return result_df

            elif method == "llm":
                if not config.get("llm_api_key"):
                    raise ValueError("大模型 API Key 未配置")
                detector = LLMDetector(
                    api_key=config["llm_api_key"],
                    base_url=config["llm_base_url"],
                    model=config["llm_model"],
                    prompt=config["llm_prompt"],
                    thinking_enabled=config.get("llm_thinking_enabled", True)
                )
                print(f"使用大语言模型 {config['llm_model']} 进行骚扰检测（思考模式{'开启' if detector.thinking_enabled else '关闭'}）...")
                harass_list, response_list, reasoning_list = detector.batch_detect(df["content"].fillna("").astype(str))
                result_df = pd.DataFrame({
                    "is_harassment": harass_list,
                    "llm_response": response_list,
                    "llm_reasoning": reasoning_list
                }, index=df.index)
                return result_df

            elif method == "both":
                keyword_file = choose_file_from_dir(config["input_dir"], ".txt")
                if not keyword_file:
                    raise FileNotFoundError("目录下不存在字典文件，开始尝试调用LLM...")
                detector = KeywordDetector(keyword_file)
                print("先使用关键词匹配...")
                is_harass = df["content"].apply(
                    lambda x: detector.is_harassment(str(x)) if pd.notna(x) else False
                )
                uncertain_mask = ~is_harass & df["content"].notna() & (df["content"].astype(str).str.strip() != "")
                uncertain_df = df[uncertain_mask]
                if len(uncertain_df) == 0:
                    print("所有评论已被关键词覆盖")
                    result_df = pd.DataFrame({
                        "is_harassment": is_harass,
                        "llm_response": "",
                        "llm_reasoning": ""
                    }, index=df.index)
                    return result_df
                print(f"关键词未命中的 {len(uncertain_df)} 条将调用大模型")
                sub_result_df = detect_harassment_with_backup(uncertain_df, config, "llm")
                final_harass = is_harass.copy()
                final_response = pd.Series("", index=df.index)
                final_reasoning = pd.Series("", index=df.index)
                for idx in uncertain_df.index:
                    final_harass.at[idx] = sub_result_df.at[idx, "is_harassment"]
                    final_response.at[idx] = sub_result_df.at[idx, "llm_response"]
                    final_reasoning.at[idx] = sub_result_df.at[idx, "llm_reasoning"]
                result_df = pd.DataFrame({
                    "is_harassment": final_harass,
                    "llm_response": final_response,
                    "llm_reasoning": final_reasoning
                }, index=df.index)
                return result_df
        except Exception as e:
            errors.append(f"{method}: {str(e)}")
            if method == "keyword" and primary_method == "llm":
                print("大模型调用失败或未配置，尝试回退到字典方法...")
            elif method == "llm" and primary_method == "keyword":
                print("目录下不存在字典文件，开始尝试调用LLM...")
            else:
                print(f"方法 {method} 失败：{e}")
            continue

    error_detail = "\n".join(errors)
    raise RuntimeError(f"骚扰检测失败，所有方法均不可用：\n{error_detail}")
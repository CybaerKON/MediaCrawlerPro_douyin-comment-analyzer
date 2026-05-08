#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大语言模型检测组件（兼容 OpenAI/DeepSeek 等）
"""

import re
import time
from typing import List, Tuple
from openai import OpenAI


class LLMDetector:
    def __init__(self, api_key: str, base_url: str, model: str,
                 prompt: str, thinking_enabled: bool = True, timeout: int = 60):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.prompt = prompt
        self.thinking_enabled = thinking_enabled
        self.timeout = timeout

    def query_single(self, comment: str) -> Tuple[bool, str, str]:
        """
        调用大模型判断单条评论是否骚扰。
        返回 (是否骚扰, 最终回答, 推理内容)
        """
        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": comment}
        ]
        max_retries = 2
        last_raw = ""
        last_reasoning = ""
        for attempt in range(1, max_retries + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    "timeout": self.timeout
                }
                if self.thinking_enabled:
                    kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    kwargs["reasoning_effort"] = "high"  # DeepSeek 特有参数，其他模型兼容可忽略
                response = self.client.chat.completions.create(**kwargs)
                reasoning = getattr(response.choices[0].message, "reasoning_content", "") or ""
                content = response.choices[0].message.content or ""
                raw_answer = content.strip()
                last_raw = raw_answer
                last_reasoning = reasoning

                short = comment[:40] + "..." if len(comment) > 40 else comment
                print(f"[LLM] {short} | 回答: {raw_answer}")

                if raw_answer == "是":
                    return True, raw_answer, reasoning
                elif raw_answer == "否":
                    return False, raw_answer, reasoning
                elif re.search(r'是', raw_answer):
                    return True, raw_answer, reasoning
                elif re.search(r'否', raw_answer):
                    return False, raw_answer, reasoning
                else:
                    print(f"警告：无法识别回答 ({raw_answer})，重试 {attempt}/{max_retries}")
                    messages.append({"role": "user", "content": "请只回答“是”或“否”，不要任何其他文字。"})
            except Exception as e:
                print(f"API 调用失败 (第{attempt}次): {e}")
                time.sleep(2)
        print(f"重试耗尽，默认为非骚扰。最终输出: {last_raw}")
        return False, last_raw, last_reasoning

    def batch_detect(self, comments: List[str]) -> Tuple[List[bool], List[str], List[str]]:
        """批量检测评论，返回 (骚扰标记列表, 回答列表, 推理列表)"""
        harass_list = []
        response_list = []
        reasoning_list = []
        total = len(comments)
        start_time = time.time()
        for i, comment in enumerate(comments, 1):
            if not comment.strip():
                harass_list.append(False)
                response_list.append("空内容")
                reasoning_list.append("")
            else:
                is_harass, raw, reasoning = self.query_single(comment)
                harass_list.append(is_harass)
                response_list.append(raw)
                reasoning_list.append(reasoning)
            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                print(f"已处理 {i}/{total} 条，耗时 {elapsed:.0f} 秒")
            time.sleep(0.3)
        return harass_list, response_list, reasoning_list
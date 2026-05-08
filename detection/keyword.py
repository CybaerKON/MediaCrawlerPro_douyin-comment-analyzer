#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词检测组件
"""

import re
from typing import List


class KeywordDetector:
    def __init__(self, keyword_file: str):
        self.keywords = self._load(keyword_file)

    def _load(self, file_path: str) -> List[str]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        keywords = [kw.strip() for kw in re.split(r'\s+', text) if kw.strip()]
        print(f"已加载 {len(keywords)} 个关键词")
        return keywords

    def is_harassment(self, content: str) -> bool:
        if not content:
            return False
        content_lower = content.lower()
        for kw in self.keywords:
            if kw.lower() in content_lower:
                return True
        return False
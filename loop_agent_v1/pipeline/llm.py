"""LLM调用层 — 引用父项目 pipeline/llm.py 的接口"""

import sys
import os

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.llm import call_light, call_heavy  # noqa: F401, E402

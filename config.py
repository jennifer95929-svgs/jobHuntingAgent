import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "ai_pm_portfolio", ".env"))

LLM_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
LLM_MODEL = os.getenv("LLM_MODEL", "ep-20260509112705-78hkm")

# 不同阶段用不同模型（默认都用 LLM_MODEL，可单独覆盖）
MODEL_LIGHT = os.getenv("MODEL_LIGHT") or LLM_MODEL    # 批量过滤/生成
MODEL_HEAVY = os.getenv("MODEL_HEAVY") or LLM_MODEL    # 推理/分析

# 投递模式: fast=跳过LLM调研直接投 deep=LLM调研公司+匹配后投
APPLY_MODE = os.getenv("APPLY_MODE", "fast")

JOB_SPREADSHEET_TOKEN = os.getenv("JOB_SPREADSHEET_TOKEN", "")
JOB_SHEET_ID = os.getenv("JOB_SHEET_ID", "9554f5")

SESSION_NAME = "job-hunter"
SEARCH_KEYWORDS = ["AI产品经理", "AI产品", "产品经理(AI方向)", "人工智能产品经理", "AI应用产品经理"]
CITIES = ["深圳", "北京", "上海", "广州", "杭州"]
MAX_APPLY_PER_DAY = 50
MAX_RETRY = 3
MIN_DELAY = 3
MAX_DELAY = 8
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
LOG_FILE = os.path.join(DATA_DIR, "agent.log")
RESUME_FILE = os.path.join(os.path.dirname(__file__), "resume", "profile.json")

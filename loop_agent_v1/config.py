import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "ai_pm_portfolio", ".env"))

LLM_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
LLM_MODEL = os.getenv("LLM_MODEL", "ep-20260509112705-78hkm")
MODEL_LIGHT = os.getenv("MODEL_LIGHT") or LLM_MODEL
MODEL_HEAVY = os.getenv("MODEL_HEAVY") or LLM_MODEL

HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "2.5"))
TICK_INTERVAL = int(os.getenv("TICK_INTERVAL", "60"))
CHAT_URL = "https://www.zhipin.com/web/geek/chat"

STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "state.json")

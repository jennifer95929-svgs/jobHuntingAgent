import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from resume.profile import load_profile, profile_summary


GREETING_TEMPLATE = """你是一位正在求职的 AI 产品经理。请根据你的简历和岗位要求，生成一段**个性化的打招呼语**。

要求：
- 语气自然、真诚，不要像模板
- 突出你与岗位的匹配点
- 控制在 100 字以内
- 不要出现"尊敬的"等过度正式用语

### 你的简历
{resume}

### 岗位信息
{job_description}

请直接输出打招呼语："""

REPLY_TEMPLATE = """你是一位正在求职的 AI 产品经理。HR 回复了你，请根据对话历史和你的简历进行回复。

要求：
- 保持自然对话节奏
- 展现专业度但不要自夸
- 回答对方问题，适当引导到你的优势
- 控制在 150 字以内

### 你的简历
{resume}

### 对话历史
{chat_history}

### HR 最新消息
{hr_message}

请直接输出回复："""


class ChatGenerator:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=0.7,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
        )

    def _generate(self, template: str, **kwargs) -> str:
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke(kwargs)

    def greeting(self, job_description: str) -> str:
        resume = profile_summary()
        msg = self._generate(
            GREETING_TEMPLATE,
            resume=resume,
            job_description=job_description,
        )
        return msg.strip()

    def reply(self, hr_message: str, chat_history: list = None) -> str:
        resume = profile_summary()
        history_str = "\n".join(chat_history[-6:]) if chat_history else "暂无对话"
        msg = self._generate(
            REPLY_TEMPLATE,
            resume=resume,
            chat_history=history_str,
            hr_message=hr_message,
        )
        return msg.strip()

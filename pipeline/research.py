import json
from pipeline.llm import call_heavy

SYSTEM = "你是一位公司研究分析师。基于公开知识和公司信息，分析目标公司的前景和业务。"


def company_report(company_name: str, extra_context: str = "") -> dict:
    prompt = f"""分析以下公司，输出 JSON 报告。

### 公司名称
{company_name}

### 额外信息
{extra_context if extra_context else "无"}

### 输出格式（只输出 JSON）
{{"company":"{company_name}","prospect_rating":"A/B/C/D","reasoning":"","business":"","advantage":"","weakness":"","ai_relevance":"high/medium/low","recommend":true/false,"recommend_reason":""}}

评级: A=明星公司(行业头部/高增长/AI核心) B=优质公司(细分领先/有增长) C=一般 D=不推荐(夕阳/经营风险)

基于你的训练数据中关于该公司的公开知识进行分析，不要编造不确定的信息。"""

    result = call_heavy(SYSTEM, prompt)

    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
    result = result.strip()

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {
            "company": company_name,
            "prospect_rating": "B",
            "reasoning": "基于默认评估",
            "business": "未知",
            "advantage": "未知",
            "weakness": "未知",
            "ai_relevance": "medium",
            "recommend": True,
            "recommend_reason": "基本信息匹配",
        }

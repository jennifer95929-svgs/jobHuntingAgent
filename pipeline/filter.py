import json
from pipeline.llm import call_light
from resume.profile import profile_summary

SYSTEM = "你是一位招聘筛选助手。严格过滤岗位，宁可漏过也不要错投。"

def batch_filter(jobs: list) -> list:
    if not jobs:
        return []

    resume = profile_summary()
    jobs_json = json.dumps([{
        "id": j.get("id"),
        "title": j.get("title"),
        "company": j.get("company", ""),
    } for j in jobs], ensure_ascii=False)

    prompt = f"""岗位筛选，宽松执行。宁可多投也不要漏过：

### 规则
1. 优先 AI产品经理 / AI产品 相关岗位，以及其他产品经理岗位
2. 公司名含"外包"/"人力派遣" → skip
3. 非产品类岗位（如Java/测试/运营/销售/客服）→ skip
4. 不确定的 → pass（后续会进一步验证公司规模和薪资）

### 候选人简历关键点
{resume}

### 岗位列表
{jobs_json}

返回 JSON 数组, 每个: {{"id": str, "decision": "pass"/"skip", "reason": str}}
只输出 JSON。"""

    result = call_light(SYSTEM, prompt)

    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
    result = result.strip()

    try:
        decisions = json.loads(result)
    except json.JSONDecodeError:
        return []

    decision_map = {d.get("id"): d for d in decisions if isinstance(d, dict)}
    passed = [j for j in jobs if decision_map.get(j.get("id"), {}).get("decision") == "pass"]
    return passed

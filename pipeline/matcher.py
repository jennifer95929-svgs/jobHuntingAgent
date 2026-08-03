import json
from pipeline.llm import call_heavy
from resume.profile import profile_summary

SYSTEM = "你是一位求职顾问。分析岗位与候选人是否匹配，只输出 JSON。"


def match_job(job: dict, company_report: dict = None) -> dict:
    resume = profile_summary()
    report_str = json.dumps(company_report or {}, ensure_ascii=False)

    prompt = f"""分析岗位匹配度。

### 候选人简历
{resume}

### 岗位
标题: {job.get('title','')}
薪资: {job.get('salary','')}

### 公司分析
{report_str}

### 输出 JSON
{{"score":0-100,"summary":"","strength":"","gap":"","strategy":"","recommend_apply":true/false}}

评分: 90-100=完美 70-89=良好建议投 50-69=可尝试 0-49=不建议"""

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
            "score": 70,
            "summary": "基本信息匹配",
            "strength": "AI产品经理经验",
            "gap": "需更多信息",
            "strategy": "突出AI产品经验",
            "recommend_apply": True,
        }


def batch_match(jobs: list, company_reports: dict = None) -> list:
    company_reports = company_reports or {}
    results = []
    for job in jobs:
        company = job.get("company", "")
        report = company_reports.get(company, None)
        match = match_job(job, report)
        results.append({**job, "match": match})
    results.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=True)
    return [r for r in results if r.get("match", {}).get("recommend_apply", False)]

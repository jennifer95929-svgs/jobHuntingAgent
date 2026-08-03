import json
import os

RESUME_FILE = os.path.join(os.path.dirname(__file__), "profile.json")

DEFAULT_PROFILE = {
    "name": "",
    "target_role": "AI 产品经理",
    "summary": "",
    "skills": {
        "product": ["产品规划", "需求分析", "PRD 撰写", "用户研究", "数据分析"],
        "ai_ml": ["AI Agent", "RAG", "Prompt Engineering", "LLM 应用开发", "模型评估"],
        "technical": ["Python", "SQL", "LangChain", "ChromaDB", "API 设计"],
        "tools": ["Figma", "Jira", "Notion", "Streamlit", "Git"]
    },
    "experience": [],
    "projects": [
        {
            "name": "AI PM Portfolio Demo",
            "desc": "竞品分析 Agent × RAG Demo，作为面试作品展示",
            "tech": ["LangChain", "RAG", "ChromaDB", "Streamlit", "Doubao LLM"]
        }
    ],
    "education": [],
    "preferred_locations": ["深圳", "北京", "上海", "广州", "杭州"],
    "preferred_salary": ""
}


def load_profile() -> dict:
    if os.path.exists(RESUME_FILE):
        try:
            with open(RESUME_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_PROFILE


def save_profile(profile: dict):
    with open(RESUME_FILE, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def profile_summary(profile: dict = None) -> str:
    p = profile or load_profile()
    parts = [
        f"目标岗位: {p.get('target_role', '')}",
        f"个人简介: {p.get('summary', '')}",
        f"产品技能: {', '.join(p['skills'].get('product', []))}",
        f"AI/ML 技能: {', '.join(p['skills'].get('ai_ml', []))}",
        f"技术技能: {', '.join(p['skills'].get('technical', []))}",
        f"工具: {', '.join(p['skills'].get('tools', []))}",
    ]
    if p.get("experience"):
        exp_strs = []
        for e in p["experience"][:2]:
            exp_strs.append(f"{e.get('company','')} - {e.get('role','')}: {e.get('desc','')}")
        parts.append("主要经历: " + " | ".join(exp_strs))
    if p.get("projects"):
        proj_strs = []
        for pr in p["projects"][:2]:
            proj_strs.append(f"{pr.get('name','')}: {pr.get('desc','')}")
        parts.append("项目: " + " | ".join(proj_strs))
    return "\n".join(parts)


def edit_profile(profile: dict = None) -> dict:
    import subprocess
    p = profile or load_profile()
    content = json.dumps(p, ensure_ascii=False, indent=2)
    editor = os.environ.get("EDITOR", "vim")
    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write(content)
    f.close()
    subprocess.call([editor, f.name])
    with open(f.name) as fh:
        try:
            new_profile = json.load(fh)
            save_profile(new_profile)
            return new_profile
        except json.JSONDecodeError as e:
            print(f"JSON 格式错误: {e}")
            return p
        finally:
            os.unlink(f.name)

#!/usr/bin/env python3
# 绘制 loop_agent_v2 当前架构图 → PNG
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm
import os

# 中文字体
for name in ["Hiragino Sans GB", "STHeiti", "Arial Unicode MS"]:
    try:
        fm.findfont(name, fallback_to_default=False)
        plt.rcParams["font.family"] = name
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loop_agent_v2_架构图.png")
W, H = 15, 10

fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def box(x, y, w, h, title, body, fc="#f5f7fa", ec="#3b7cbf", tfs=11, bfs=8.5, title_color="#1f3a5f"):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
                       fc=fc, ec=ec, lw=1.5)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top",
            fontsize=tfs, fontweight="bold", color=title_color)
    ax.text(x + w / 2, y + h - 0.62, body, ha="center", va="top",
            fontsize=bfs, color="#333333", linespacing=1.45)


def arrow(x1, y1, x2, y2, label="", color="#7f7f7f", radius=0.0):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16,
                        color=color, lw=1.6, connectionstyle=f"arc3,rad={radius}")
    ax.add_patch(a)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.1, my + 0.12, label, fontsize=8.5, color="#444",
                ha="center", va="bottom")


# ===== 标题 =====
ax.text(W / 2, H - 0.35, "候选 agent V2 当前架构 —— LLM 决策 + 代码只做工具/接线",
        ha="center", fontsize=15, fontweight="bold", color="#1f3a5f")

# ===== 顶部:5xMD 系统提示词 =====
ax.text(0.5, H - 1.15, "系统提示词 = 5 份 MD(大脑)", fontsize=11, fontweight="bold", color="#333")
md_files = [("GOAL", "使命"), ("DOMAIN", "页面/选择器"), ("RULES", "决策流程+防风控"),
            ("PROFILE", "简历"), ("WORKFLOW", "步骤")]
md_x = 1.0
for name, desc in md_files:
    box(md_x, H - 2.0, 2.5, 0.85, f"{name}.md",
        f"职责:{desc}\n(纯文字,零代码)", fc="#eef3fa", ec="#5b8cc9", bfs=8)
    md_x += 2.75

# ===== 主循环 loop.py(上方居中) =====
loop_y = H - 4.4
box(5.4, loop_y, 4.2, 1.3, "loop.py  (循环脚手架)",
    "for i in range(护栏40):\n  capture → LLM → execute → save\n  累积 history 回传",
    fc="#e8f4e8", ec="#4c8c4c")

# ===== 左侧:context.py =====
box(0.7, 2.4, 3.0, 1.4, "context.py",
    "capture():真浏览器读现状\n url/未读数/页面文本/state\n (零业务判断)", fc="#fdf6e3", ec="#c9a227")
arrow(5.4, loop_y + 0.5, 3.7, 3.2, "capture()", radius=0.15)

# ===== 中间:llm.py =====
box(4.9, 1.1, 3.2, 1.4, "llm.py",
    "工具调用桥接\n 调 DeepSeek(litellm:4000)\n 解析 tool_use 返回 {name,args}",
    fc="#e3ebf7", ec="#3b7cbf")
arrow(7.6, loop_y - 0.2, 7.6, 2.5, "LLM 返回决定", radius=0.0)
arrow(5.4, loop_y - 0.2, 5.8, 2.5, "带工具清单+历史", radius=0.0)

# ===== eslite: model =====
box(8.7, 1.1, 3.6, 1.4, "DeepSeek (真模型)",
    "通过 litellm → deepseek-chat\n 读 MD + 现场状态\n 自主输出下一个工具调用",
    fc="#fdecea", ec="#c04040")
arrow(8.1, 1.8, 8.65, 1.8, "", radius=0.0)
arrow(8.1, 1.4, 8.65, 1.4, "", radius=0.0)
ax.text(8.38, 1.6, "双向(调/回)", fontsize=7.5, ha="center", color="#788")

# ===== 底部:tools.py → 浏览器驱动 =====
box(0.7, 0.5, 4.4, 1.5, "tools.py (8×只读工具)",
    "search_jobs / scan_page / inspect_company\ncheck_messages / page_text / screenshot\nwait / done      (无 apply、无业务 if)",
    fc="#eef3fa", ec="#5b8cc9")
arrow(7.6, 5.0 - 0.0, 7.6, 2.5, "", color="#bbc", radius=0.0)  # loop→llm 已做
# loop → tools 执行
arrow(8.0, loop_y - 0.2, 5.1, 2.0, "execute 派发", radius=0.25)

box(5.7, 0.5, 3.6, 1.5, "浏览器驱动(复用V1)",
    "BossSession / CDP\n Chrome --remote-debugging-port=9222\n 真实登录态·真实页面",
    fc="#f3edfb", ec="#8a5bbf")
arrow(5.1, 1.3, 5.68, 1.3, "调工具", color="#5b8cc9")

box(9.8, 0.5, 3.6, 1.5, "salary_decode.py",
    "canvas 字形识别\n 还原 BOSS 薪资 PUA 乱码\n (纯工具,无决策)",
    fc="#fff4e6", ec="#d2864a")
arrow(5.7, 1.3, 5.68, 1.3, "", color="#fff")  # spacer


# ===== 底部注释 =====
ax.text(W/2, 0.02, "决策主体=DeepSeek(读MD自主) · 代码=纯工具+接线 · 只读联调(无投递)",
        ha="center", fontsize=9, color="#666")

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print("saved:", OUT)

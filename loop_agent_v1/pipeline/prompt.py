"""指令模板 — 构建注入给 AI 的结构化指令 prompt"""


def build_reply_instruction(company: str, hr_name: str, hr_message: str, reply_draft: str) -> str:
    return f"""执行以下BOSS直聘回复任务：

目标公司: {company}
HR: {hr_name}
HR消息: {hr_message}

预拟回复:
{reply_draft}

操作步骤:
1. 在聊天列表中找到 {company} 的对话并点击
2. 确认聊天区域切换到 {company}
3. 在输入框中输入预拟回复
4. 点击发送按钮
5. 确认消息已发送

完成后报告结果。"""


def build_check_instruction() -> str:
    return """执行以下BOSS直聘检查任务：

1. 打开BOSS直聘聊天页面
2. 检测是否有未读消息（红点badge）
3. 如有未读，逐个打开读取消息内容
4. 检测是否有交换卡片（微信/电话）
5. 如有交换卡片，判断岗位是否合适，合适则点击同意

完成后报告结果。"""

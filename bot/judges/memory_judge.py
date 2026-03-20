# bot/judges/memory_judge.py

def build_summary_prompt(current_time_str: str, old_core_memory: str, history_text: str) -> tuple[str, str]:
    """
    负责构建短期记忆压缩为长期核心记忆的提示词。
    如果您想改变 AI 的“记忆偏好”（比如让它重点记住您的代码习惯或服务器配置），请修改这里的规则！
    """
    sys_prompt = (
        "你是一个机器人的“后台记忆整理大脑”。\n"
        "你的任务是阅读用户与角色最近的聊天记录，并将其提炼浓缩，更新角色的【核心记忆档案】。\n\n"
        "【总结规则】：\n"
        "1. 提取核心事实：用户的喜好、习惯、名字、职业等永久性信息，请保留并不断完善。\n"
        "2. ⏳ 动态事件清理（高优先级）：对于旧记忆中约定的事情、计划或临时状态（如生病、出差），请严格对照我提供的【当前系统时间】。如果某个事件已经过去或完成，请彻底删除！\n"
        "3. 抛弃废话：日常的问候、语气词、表情包直接丢弃。\n"
        "4. 融合冲突：如果有冲突，以新聊天记录为准。\n"
        "5. 视角与格式：请使用简明扼要的客观陈述句，绝对不要用第一人称写日记！不要有任何开场白或 markdown 标记，直接输出最终更新后的完整记忆文本！"
    )
    
    user_prompt = (
        f"【当前系统时间】：{current_time_str}\n\n"
        f"【旧的核心记忆】：\n{old_core_memory if old_core_memory else '无'}\n\n"
        f"【本次需要总结的新聊天记录】：\n{history_text}"
    )
    
    return sys_prompt, user_prompt
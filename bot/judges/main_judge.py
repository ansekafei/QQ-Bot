# bot/judges/main_judge.py
from datetime import datetime

def build_main_system_prompt(active_prompt: str, core_mem: str, recent_track: str, 
                             daily_schedule: str, sticker_addon: str, tool_prompt: str, 
                             system_prompt_addon: str) -> str:
    """
    主脑生成回复的核心提示词构建器。
    如果您需要修改 AI 聊天的根本规则、字数限制或行为规范，请修改这里！
    """
    dynamic_prompt = active_prompt + f"\n\n【当前真实时间】：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"
    
    if core_mem and "暂无核心" not in core_mem: 
        dynamic_prompt += f"\n\n【核心记忆】\n{core_mem}"
        
    dynamic_prompt += f"\n\n【近期轨迹】\n{recent_track}"
    
    if daily_schedule: 
        dynamic_prompt += f"\n\n【今日日记参考】\n{daily_schedule}"

    # ---------------- 核心行为规则区 ---------------- #
    dynamic_prompt += "\n\n【绝对输出规则】：\n1. 严格身处当前时间，禁止预知未来！\n2. 聊天必须简短自然！如果你要写代码或配置文件，请务必用 ``` 包裹起来。"
    dynamic_prompt += "\n\n【特殊指令】：如果达成约定，输出 `[RECORD_PROMISE: 事件]` ！"
    # ------------------------------------------------ #
    
    dynamic_prompt += sticker_addon
    dynamic_prompt += tool_prompt + system_prompt_addon

    return dynamic_prompt
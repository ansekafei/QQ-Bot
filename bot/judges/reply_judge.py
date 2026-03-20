# bot/judges/reply_judge.py
import re
from datetime import datetime
from core.config import cfg
from core.logger import logger

async def evaluate_should_reply(combined_text: str, schedule_info: str, get_client_func) -> tuple[bool, str, float]:
    """
    判断当前是否应该回复用户。
    修改这里的 prompt 可以改变 AI 对“忙碌”或“摸鱼”的判定标准。
    """
    client = get_client_func(cfg.get("summary_gateway", 1))
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    prompt = (
        f"你是一个无情的日程状态判断机器。请根据【当前时间】与【今日日程】，严格判断角色现在是否有空聊天。\n"
        f"【当前时间】：{current_time_str}\n"
        f"【今日日程】：\n{schedule_info if schedule_info else '暂无特别安排'}\n"
        f"【用户消息】：{combined_text}\n\n"
        f"严格输出规则：\n"
        f"1. 如果当前处于休息、娱乐、摸鱼、吃饭或无安排的【空闲】状态，请直接且仅输出两个英文字母：YES\n"
        f"2. 如果当前处于睡觉、上课、工作、开会等无法看手机的【忙碌】状态，请计算距离下一次有空还需要几小时(保留1位小数)，并严格按照此格式输出：NO|小时数 （例如：NO|2.5）\n"
        f"绝对禁止输出任何其他文字或标点！"
    )
    
    try:
        resp = await client.chat.completions.create(
            model=cfg.get("summary_model"), 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0.0, 
            max_tokens=20,
            timeout=8.0  
        )
        ans = (resp.choices[0].message.content or "YES").strip().upper()
        
        if "NO" in ans:
            try: delay_hours = float(re.search(r'\d+(\.\d+)?', ans).group())
            except Exception: delay_hours = 1.0
            return False, f"日程繁忙，延迟 {delay_hours} 小时", delay_hours
        else:
            return True, "当前空闲", 0.0
            
    except Exception as e:
        logger.error(f"⚠️ 裁判网络卡顿(超时)，默认放行: {repr(e)}")
        return True, "报错降级放行", 0.0
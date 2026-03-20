# bot/judges/image_judge.py
import re
from core.config import cfg
from core.logger import logger
from bot.tools.image_generator import image_generator

async def evaluate_and_generate_image(reply_text: str, daily_schedule: str, get_client_func) -> str:
    """
    判断 AI 的回复是否需要配一张生活照。
    修改这里的 prompt 可以改变 AI 发送照片的频率或画风要求。
    """
    try:
        judge_client = get_client_func(cfg.get("summary_gateway", 1))
        
        image_judge_prompt = f"""你是一个配图裁判。
【AI准备发送的回复】：{reply_text}
【当前的活动日程】：{daily_schedule if daily_schedule else '暂无'}

如果回复明确同意发照片或有类似视觉标签，请构思一张极具生活感的日常随拍。
严格独立一行输出: [IMAGE: 画面主体描述, 穿搭细节, 环境, 摄影风格]
如果不符合，只输出: [NO]"""
        
        judge_resp = await judge_client.chat.completions.create(
            model=cfg.get("summary_model"),
            messages=[{"role": "user", "content": image_judge_prompt}],
            temperature=0.3, 
            timeout=8.0
        )
        
        ans = judge_resp.choices[0].message.content or "[NO]"
        img_match = re.search(r'\[IMAGE:\s*(.*?)\]', ans)
        
        if img_match:
            logger.info(f"📸 [配图裁判] 审核通过，拉起生图: {img_match.group(1)}")
            return await image_generator.generate_life_photo(img_match.group(1).strip())
            
    except Exception as e:
        logger.error(f"⚠️ [配图裁判] 异常: {e}")
        
    return ""
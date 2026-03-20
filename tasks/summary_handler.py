# tasks/summary_handler.py
import json
from datetime import datetime
from core.logger import logger
from bot.memory_manager import memory_manager
from core.config import cfg

# 🌟 折中修复 1：全局总结锁，绝对防并发防踩踏
_is_summarizing = False

async def summarize_memory_async():
    global _is_summarizing
    
    if _is_summarizing:
        logger.info("⏳ [记忆系统] 另一个记忆总结任务正在运行，已跳过防踩踏...")
        return False, "正在总结中"
        
    _is_summarizing = True
    try:
        logger.info("🧠 [记忆系统] 触发短期记忆总结机制，正在整理并提炼核心记忆...")
        from bot.brain import brain
        client = brain.get_client()
        
        history = await memory_manager.load_history()
        if not history or len(history) < 2:
            return False, "当前记忆太少，无需总结"
            
        old_core_memory = await memory_manager.load_core_memory()
        if old_core_memory == "暂无核心记忆。":
            old_core_memory = ""
            
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        current_time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        summary_model = cfg.get("summary_model")
        
        sys_prompt = (
            "你是一个机器人的“后台记忆整理大脑”。\n"
            "你的任务是阅读用户与角色最近的聊天记录，并将其提炼浓缩，更新角色的【核心记忆档案】。\n\n"
            "【总结规则】：\n"
            "1. 提取核心事实：用户的喜好、习惯、名字、职业等永久性信息，请保留并不断完善。\n"
            "2. ⏳ 动态事件清理（高优先级）：对于旧记忆中约定的事情、计划或临时状态（如生病、出差），请严格对照我提供的【当前系统时间】。如果某个事件的时间节点已经过去、或者事件已经完成，请直接从记忆中将其彻底删除，不要保留任何痕迹！\n"
            "3. 抛弃无用的废话：日常的问候、语气词、表情包、无关紧要的闲聊直接丢弃。\n"
            "4. 融合冲突：如果有冲突（比如用户改名了），以新聊天记录为准。\n"
            "5. 视角与格式：请使用简明扼要的客观陈述句，绝对不要用第一人称写日记！不要有任何开场白或 markdown 标记，直接输出最终更新后的完整记忆文本！"
        )
        
        user_prompt = (
            f"【当前系统时间】：{current_time_str}\n\n"
            f"【旧的核心记忆】：\n{old_core_memory if old_core_memory else '无'}\n\n"
            f"【本次需要总结的新聊天记录】：\n{history_text}"
        )

        response = await client.chat.completions.create(
            model=summary_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2, 
            timeout=60.0
        )
        
        new_core_memory = response.choices[0].message.content.strip()
        new_core_memory = new_core_memory.replace('```json', '').replace('```text', '').replace('```', '').strip()
        
        await memory_manager.save_core_memory(new_core_memory)
        retain_history = history[-20:] if len(history) > 20 else []
        async with memory_manager._lock:
            await memory_manager.save_history(retain_history) 
        
        logger.info("🧠 [记忆系统] 总结与过期事件清理完成！保留了最后 20 条近期对话。")
        return True, "短期记忆总结成功，过期事件已自动清理。"
        
    except Exception as e:
        logger.error(f"❌ [记忆系统] 总结执行失败: {e}")
        return False, f"总结失败: {str(e)}"
    finally:
        # 🌟 无论 API 是否超时报错崩溃，最终一定释放锁，防止永久失忆
        _is_summarizing = False
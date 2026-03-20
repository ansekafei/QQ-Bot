# tasks/summary_handler.py
import json
from datetime import datetime
from core.logger import logger
from bot.memory_manager import memory_manager
from core.config import cfg
from bot.judges.memory_judge import build_summary_prompt

# 🌟 修复保留项：全局总结锁，绝对防并发防踩踏
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
        
        # 🌟 直接向裁判所请求 Prompt
        sys_prompt, user_prompt = build_summary_prompt(current_time_str, old_core_memory, history_text)

        summary_model = cfg.get("summary_model")
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
        _is_summarizing = False
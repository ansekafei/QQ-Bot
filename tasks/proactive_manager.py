# tasks/proactive_manager.py
import asyncio
import random
import re
from datetime import datetime, timedelta

from core.config import cfg
from core.logger import logger
from bot.memory_manager import memory_manager
from tasks.schedule_manager import schedule_manager
from bot.tools.tool_manager import execute_search, get_tool_prompt

# 🌟 引入刚刚分离的裁判引擎
from bot.judges.proactive_judge import build_proactive_prompt, build_morning_greeting_prompt

class ProactiveManager:
    def __init__(self):
        self.last_interaction_time = datetime.now()
        self.next_proactive_time = None

    def update_interaction_time(self):
        self.last_interaction_time = datetime.now()
        min_hours = cfg.get("proactive_min_hours", 8.0)
        max_hours = cfg.get("proactive_max_hours", 16.0)
        random_hours = random.uniform(min_hours, max_hours)
        self.next_proactive_time = self.last_interaction_time + timedelta(hours=random_hours)
        logger.info(f"⏰ [主动搭话] 已排期：预计在 {self.next_proactive_time.strftime('%Y-%m-%d %H:%M:%S')} 尝试主动联系。")

    def set_custom_proactive_delay(self, hours: float):
        self.last_interaction_time = datetime.now()
        hours = max(0.25, min(hours, 12.0))
        self.next_proactive_time = self.last_interaction_time + timedelta(hours=hours)
        logger.info(f"⏰ [延迟回复] AI判断暂时没空。已自动排期在约 {int(hours*60)} 分钟后回复！")

    def is_in_dnd_period(self):
        dnd_start = cfg.get("dnd_start_time", "23:00")
        dnd_end = cfg.get("dnd_end_time", "08:00")
        now = datetime.now()
        current_time = now.time()
        try:
            start_time = datetime.strptime(dnd_start, "%H:%M").time()
            end_time = datetime.strptime(dnd_end, "%H:%M").time()
        except ValueError:
            return False
        if start_time > end_time: 
            return current_time >= start_time or current_time <= end_time
        else: 
            return start_time <= current_time <= end_time

    async def proactive_background_task(self):
        self.update_interaction_time()
        
        while True:
            await asyncio.sleep(60 * 3) 
            if not cfg.get("proactive_enabled", True): 
                continue
                
            now = datetime.now()
            if self.next_proactive_time and now >= self.next_proactive_time:
                if self.is_in_dnd_period():
                    logger.info("🤫 [主动搭话] 到达触发时间，但处于免打扰时段，推迟1小时后再试...")
                    self.next_proactive_time = now + timedelta(hours=1)
                    continue
                    
                await self.trigger_proactive_message()
                self.update_interaction_time()

    async def trigger_proactive_message(self):
        from bot.brain import brain
        from bot.qq_client import send_qq_msg
        
        logger.info("💖 [主动搭话] 触发主动问候机制！开始构思...")
        allowed_users_str = cfg.get("allowed_users", "").strip()
        if not allowed_users_str: 
            return
            
        user_id = allowed_users_str.split(',')[0].strip()
        hours_passed = (datetime.now() - self.last_interaction_time).total_seconds() / 3600

        dynamic_system_prompt = await memory_manager.load_active_prompt()
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        dynamic_system_prompt += f"\n\n【系统附加设定】当前的现实时间是：{current_time}。"
        
        core_mem = await memory_manager.load_core_memory()
        if core_mem and "暂无核心" not in core_mem:
            dynamic_system_prompt += f"\n\n【核心记忆】\n{core_mem}"
            
        dynamic_system_prompt += f"\n\n【近期生活轨迹记忆表】\n{await schedule_manager.get_recent_table_md()}"
        
        daily_schedule = await schedule_manager.get_todays_schedule()
        if daily_schedule: 
            dynamic_system_prompt += f"\n\n【今日日记参考(时间轴)】\n{daily_schedule}"
        
        dynamic_system_prompt += get_tool_prompt()

        # 🌟 动态获取搭话指令
        dynamic_system_prompt += build_proactive_prompt(hours_passed)

        current_history = await memory_manager.load_history()
        messages_to_send = [{"role": "system", "content": dynamic_system_prompt}] + current_history

        client = brain.get_client()
        try:
            response = await client.chat.completions.create(
                model=cfg.get("chat_model"), 
                messages=messages_to_send, 
                temperature=0.7
            )
            reply = response.choices[0].message.content
            
            clean_reply = re.sub(r'\[表情包:.*?\]', '', reply).strip()
            clean_reply = re.sub(r'\[RECORD_PROMISE:.*?\]', '', clean_reply).strip()

            reply_time_stamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
            await memory_manager.append_memory("assistant", f"{reply_time_stamp} (主动发起) {clean_reply}")
            
            paragraphs = re.split(r'\n+', clean_reply)
            for para in paragraphs:
                para = para.strip()
                if not para: continue
                delay = min(len(para) * 0.25, 12.0) + 1.5
                await asyncio.sleep(delay)
                await send_qq_msg(user_id, para, 'private')
                logger.info(f"💬 发送主动气泡: {para[:20]}...")
                
        except Exception as e:
            logger.error(f"❌ [主动搭话] 生成或发送失败: {e}")

    async def daily_weather_task(self):
        from bot.brain import brain
        from bot.qq_client import send_qq_msg
        
        while True:
            now = datetime.now()
            schedule = await schedule_manager.get_todays_schedule()
            if not schedule:
                logger.info("📝 正在为您规划今日生活轨迹安排与结构化记忆...")
                await schedule_manager.generate_daily_schedule()
                
            wake_up_str = await schedule_manager.get_today_wakeup_time()
            try:
                wake_hour, wake_min = map(int, wake_up_str.replace("：", ":").split(":"))
            except:
                wake_hour, wake_min = 8, 0
                
            target = now.replace(hour=wake_hour, minute=wake_min, second=0, microsecond=0)
            
            if now >= target:
                next_day = now + timedelta(days=1)
                midnight_target = next_day.replace(hour=0, minute=1, second=0, microsecond=0)
                sleep_seconds = (midnight_target - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                continue
                
            sleep_seconds = (target - now).total_seconds()
            logger.info(f"🌤️ [作息引擎] 闹钟已设定！她将在今天 {wake_up_str} 准时苏醒播报早安。")
            
            await asyncio.sleep(sleep_seconds)
            
            logger.info("🌤️ [定时任务] 正在执行每日早安与天气查询...")
            allowed_users_str = cfg.get("allowed_users", "").strip()
            if not allowed_users_str: 
                continue
            user_id = allowed_users_str.split(',')[0].strip()

            search_result = await execute_search("今日当地天气预报", ignore_limit=True)
            dynamic_system_prompt = await memory_manager.load_active_prompt()
            
            fresh_schedule = await schedule_manager.get_todays_schedule()
            if fresh_schedule:
                dynamic_system_prompt += f"\n\n【今日日记参考(时间轴)】\n{fresh_schedule}"
            
            # 🌟 动态获取早安问候指令
            dynamic_system_prompt += build_morning_greeting_prompt(search_result)

            client = brain.get_client()
            try:
                response = await client.chat.completions.create(
                    model=cfg.get("chat_model"), 
                    messages=[{"role": "system", "content": dynamic_system_prompt}], 
                    temperature=0.7
                )
                reply = response.choices[0].message.content
                clean_reply = re.sub(r'\[.*?\]', '', reply).strip()
                
                await memory_manager.append_memory("assistant", f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] (早安播报) {clean_reply}")
                
                paragraphs = re.split(r'\n+', clean_reply)
                for para in paragraphs:
                    para = para.strip()
                    if not para: continue
                    delay = min(len(para) * 0.25, 12.0) + 1.5
                    await asyncio.sleep(delay)
                    await send_qq_msg(user_id, para, 'private')
                    logger.info(f"💬 发送早安气泡: {para[:20]}...")
                    
            except Exception as e:
                logger.error(f"❌ 早安播报失败: {e}")
                
            await asyncio.sleep(60)

proactive_manager = ProactiveManager()
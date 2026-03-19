# tasks/schedule_manager.py
import os
import json
import asyncio
import re
from datetime import datetime, timedelta

from core.file_io import async_read_json, async_write_json
from core.config import cfg
from core.logger import logger
from bot.memory_manager import memory_manager

HISTORY_FILE = "data/life_history.json"

class ScheduleManager:
    async def load_history(self) -> dict:
        return await async_read_json(HISTORY_FILE, default={})

    async def save_history(self, data: dict):
        await async_write_json(HISTORY_FILE, data)

    def clean_old_history(self, data: dict) -> dict:
        """维护表格：只保留最近 7 天的记忆"""
        sorted_dates = sorted(data.keys())
        if len(sorted_dates) > 7:
            for d in sorted_dates[:-7]:
                del data[d]
        return data

    async def get_recent_table_md(self) -> str:
        """生成供大模型读取的 Markdown 表格"""
        data = await self.load_history()
        if not data: 
            return "暂无历史生活数据。"
        
        md = "| 日期 | 起床时间 | 穿搭打扮 | 记录的约定/待办 |\n|---|---|---|---|\n"
        for date in sorted(data.keys()):
            info = data[date]
            promises = "，".join(info.get("promises", [])) if info.get("promises") else "无"
            md += f"| {date} | {info.get('wake_up_time', '未知')} | {info.get('outfit', '未知')} | {promises} |\n"
        return md

    async def generate_daily_schedule(self, force=False) -> str:
        """调用大模型动态生成今天的日程与作息"""
        from bot.brain import brain 
        client = brain.get_client()
        chat_model = cfg.get("chat_model")
        sys_prompt = await memory_manager.load_active_prompt()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        history_data = await self.load_history()
        
        if not force and today_str in history_data and history_data[today_str].get("schedule_text"):
            return history_data[today_str]["schedule_text"]

        recent_table = await self.get_recent_table_md()
        
        instruction = f"""【系统高优先级任务：生成今日生活轨迹与结构化记忆表】
请你以当前被设定的角色身份，规划“今天({today_str})”的生活作息表。

【过去7天的记忆表格参考】（请避免今天穿和前几天完全一样的衣服，并记得把你之前记录的约定安排进今天的日程中）：
{recent_table}

【规划要求】：
1. 几点钟起床？（请具体到时间，如 08:30，系统将严格在此时唤醒你给你发早安）。
2. 今天的穿衣打扮是什么？
3. 起床后的固定安排（必须包含查天气并主动发消息关心用户）。
4. 今天的三餐与具体活动安排。
5. 今晚几点睡？睡前做什么？

⚠️ 【严格 JSON 格式要求，绝对不要包含 ```json 标记，必须按以下字典数组输出】：
{{
    "wake_up_time": "08:30",
    "outfit": "今天的穿搭描述（简明扼要）",
    "schedule_events": [
        {{"time": "08:30", "content": "唔…闹钟响了，再赖五分钟…(揉眼睛) 好吧，起床！"}},
        {{"time": "08:45", "content": "洗漱完啦，第一件事就是看手机！查一下天气然后发消息提醒你~"}},
        {{"time": "12:00", "content": "去食堂吃午饭，今天想吃麻辣烫！"}},
        {{"time": "14:00", "content": "去图书馆自习，要把昨天没完成的作业写完！"}},
        {{"time": "23:30", "content": "困啦，跟你说完晚安就睡觉觉。"}}
    ],
    "promises": ["未完成的约定提取", "今天新产生的打算"]
}}"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=chat_model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": instruction}
                    ],
                    temperature=0.8,
                    timeout=60.0 
                )
                raw_content = response.choices[0].message.content.strip()
                
                start_idx = raw_content.find('{')
                end_idx = raw_content.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    schedule_data = json.loads(raw_content[start_idx:end_idx])
                else:
                    raise ValueError("未能提取出有效的 JSON")
                
                events = schedule_data.get("schedule_events", [])
                if isinstance(events, list) and len(events) > 0:
                    schedule_text = "\n".join([f"【{e.get('time', '00:00')}】 {e.get('content', '')}" for e in events])
                else:
                    schedule_text = schedule_data.get("schedule_text", "今天没有特别的安排，随性过一天。")
                
                history_data[today_str] = {
                    "wake_up_time": schedule_data.get("wake_up_time", "08:00"),
                    "outfit": schedule_data.get("outfit", "日常居家服"),
                    "schedule_text": schedule_text,
                    "promises": schedule_data.get("promises", [])
                }
                
                history_data = self.clean_old_history(history_data)
                await self.save_history(history_data)
                
                logger.info(f"📅 [生活轨迹] 今日排期生成成功！自动起床时间设为: {history_data[today_str]['wake_up_time']}")
                
                # 🌟 核心优化：生成完日记后，自动触发一次约定清理！
                # 这会读取刚生成的最新约定和过去的约定，去除过期的，并重新合并存档
                logger.info("🧹 [自动清理] 正在同步整理并清理过期的待办/约定...")
                await self.clean_outdated_promises()
                
                return schedule_text
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 结构化表单生成异常 ({e})，正在重试...")
                    await asyncio.sleep(5)
                else:
                    logger.error(f"❌ 连续生成失败，启动兜底机制: {e}")
                    return ""
        return ""

    async def get_todays_schedule(self) -> str:
        today_str = datetime.now().strftime("%Y-%m-%d")
        data = await self.load_history()
        return data.get(today_str, {}).get("schedule_text", "")

    async def get_today_wakeup_time(self) -> str:
        today_str = datetime.now().strftime("%Y-%m-%d")
        data = await self.load_history()
        return data.get(today_str, {}).get("wake_up_time", "08:00")

    async def add_promise(self, promise_text: str):
        today_str = datetime.now().strftime("%Y-%m-%d")
        data = await self.load_history()
        if today_str not in data:
            data[today_str] = {"wake_up_time": "08:00", "outfit": "未知", "schedule_text": "未生成", "promises": []}
        if "promises" not in data[today_str]:
            data[today_str]["promises"] = []
            
        data[today_str]["promises"].append(promise_text)
        await self.save_history(data)
        logger.info(f"📝 已将约定写入今日表格：{promise_text}")

    async def clean_outdated_promises(self) -> tuple[bool, str]:
        from bot.brain import brain
        client = brain.get_client()
        summary_model = cfg.get("summary_model")
        
        data = await self.load_history()
        today_str = datetime.now().strftime("%Y-%m-%d")
        current_time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 提取过去所有日期中的约定去重
        all_promises = []
        for date, info in data.items():
            for p in info.get("promises", []):
                if p not in all_promises:
                    all_promises.append(p)
                    
        if not all_promises:
            return True, "当前没有任何待办/约定，无需清理。"
            
        sys_prompt = "你是一个智能助理的后台数据清理程序。你的任务是审查用户记录的【待办事项/约定】列表，并根据【当前系统时间】删除已经过期、失效或没有保留价值的待办事项。"
        user_prompt = (
            f"【当前系统时间】：{current_time_str}\n\n"
            f"【待办事项列表】：\n{json.dumps(all_promises, ensure_ascii=False)}\n\n"
            f"请输出一个纯 JSON 字符串数组（不要 markdown 标记），只包含【未来需要做】或【依然有效】的待办事项。如果全都过期了，请输出 []。"
        )

        try:
            response = await client.chat.completions.create(
                model=summary_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                timeout=60.0
            )
            raw_content = response.choices[0].message.content.strip()
            raw_content = raw_content.replace('```json', '').replace('```', '').strip()
            
            start_idx = raw_content.find('[')
            end_idx = raw_content.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                valid_promises = json.loads(raw_content[start_idx:end_idx])
            else:
                return False, "大模型返回的格式不正确，清理失败。"
                
            if not isinstance(valid_promises, list):
                valid_promises = []
                
            # 🧹 清理所有历史日期的约定，将有效项“沉淀”到今天
            for date in data.keys():
                data[date]["promises"] = []
                
            if today_str not in data:
                data[today_str] = {"wake_up_time": "08:00", "outfit": "未知", "schedule_text": "未生成", "promises": []}
                
            data[today_str]["promises"] = valid_promises
            await self.save_history(data)
            
            logger.info(f"🧹 [记忆系统] 约定清理完成！共清理 {len(all_promises) - len(valid_promises)} 条过期记录。")
            return True, f"整理完成！成功清理了 {len(all_promises) - len(valid_promises)} 条过期事项。"
            
        except Exception as e:
            logger.error(f"❌ 约定清理失败: {e}")
            return False, f"清理出错: {str(e)}"

schedule_manager = ScheduleManager()
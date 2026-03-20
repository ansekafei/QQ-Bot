# bot/brain.py
import re
import asyncio
from datetime import datetime
from openai import AsyncOpenAI

from core.config import cfg
from core.logger import logger
from bot.memory_manager import memory_manager
from tasks.schedule_manager import schedule_manager
from bot.tools.sticker_manager import sticker_manager
from bot.tools.tool_manager import get_tool_prompt, execute_search

# 🌟 引入解耦后的三大独立裁判模块
from bot.judges.reply_judge import evaluate_should_reply
from bot.judges.image_judge import evaluate_and_generate_image
from bot.judges.main_judge import build_main_system_prompt

class BotBrain:
    def __init__(self):
        self._clients = {1: None, 2: None}
        self._config_caches = {1: None, 2: None}

    def get_client(self, gateway_index=1):
        gateway_index = int(gateway_index)
        if gateway_index == 2:
            base_url = cfg.get("base_url_2", "")
            api_key = cfg.get("api_key_2", "")
        else:
            base_url = cfg.get("base_url", "")
            api_key = cfg.get("api_key", "")
            
        if base_url and not base_url.endswith('/'):
            base_url += '/'
        
        current_config = (base_url, api_key)
        if self._clients[gateway_index] is None or self._config_caches[gateway_index] != current_config:
            self._clients[gateway_index] = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._config_caches[gateway_index] = current_config

        return self._clients[gateway_index]

    async def judge_should_reply(self, combined_text: str, schedule_info: str) -> tuple[bool, str, float]:
        # 移交独立文件处理
        return await evaluate_should_reply(combined_text, schedule_info, self.get_client)

    async def generate_reply(self, current_history: list, system_prompt_addon: str):
        client = self.get_client(cfg.get("chat_gateway", 1))
        
        # 使用独立文件动态组装提示词
        dynamic_prompt = build_main_system_prompt(
            active_prompt=await memory_manager.load_active_prompt(),
            core_mem=await memory_manager.load_core_memory(),
            recent_track=await schedule_manager.get_recent_table_md(),
            daily_schedule=await schedule_manager.get_todays_schedule(),
            sticker_addon=await sticker_manager.get_system_prompt_addon(),
            tool_prompt=get_tool_prompt(),
            system_prompt_addon=system_prompt_addon
        )

        messages = [{"role": "system", "content": dynamic_prompt}] + current_history

        try:
            response = await client.chat.completions.create(
                model=cfg.get("chat_model"), messages=messages, temperature=0.7, timeout=120.0
            )
            reply_text = response.choices[0].message.content or "..."
    
            search_depth = 0
            while search_depth < 3:
                search_match = re.search(r'\[SEARCH:\s*(.*?)\]', reply_text)
                if not search_match: break
                search_query = search_match.group(1).strip()
                search_result = await execute_search(search_query)
                messages.extend([
                    {"role": "assistant", "content": reply_text}, 
                    {"role": "system", "content": f"关于 '{search_query}' 的结果:\n{search_result}\n\n请直接回答。"}
                ])
                response = await client.chat.completions.create(
                    model=cfg.get("chat_model"), messages=messages, temperature=0.7, timeout=120.0
                )
                reply_text = response.choices[0].message.content or "..."
                search_depth += 1
    
            for promise in re.findall(r'\[RECORD_PROMISE:\s*(.*?)\]', reply_text):
                await schedule_manager.add_promise(promise)
                
            clean_reply = re.sub(r'\[RECORD_PROMISE:.*?\]|\[SEARCH:.*?\]|\[视觉能力触发\]|\[发送照片\]', '', reply_text).strip()
            sticker_tags = re.findall(r'\[表情包:(.*?)\]', clean_reply)
            clean_reply = re.sub(r'\[表情包:.*?\]', '', clean_reply).strip()
            clean_reply = re.sub(r'\[(?:\d{4}-)?\d{2}-\d{2}\s\d{2}:\d{2}\]\s*', '', clean_reply).strip()
            clean_reply = re.sub(r'\[PHOTO_GENERATION_PROMPT:.*?\]|\[IMAGE:.*?\]', '', clean_reply, flags=re.IGNORECASE|re.DOTALL).strip()
            
            # 代码块保护
            code_blocks = []
            def code_replacer(match):
                code_blocks.append(match.group(0))
                return f"\n\n[__CODE_BLOCK_{len(code_blocks)-1}__]\n\n"
            clean_reply = re.sub(r'```[\s\S]*?```', code_replacer, clean_reply)

            # 移交独立文件处理配图
            image_cq_code = await evaluate_and_generate_image(reply_text, daily_schedule, self.get_client)
            
            await memory_manager.append_memory("assistant", f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {reply_text}")
    
            raw_paras = re.split(r'\n+', clean_reply)
            merged_paras, current_bubble = [], ""
            for p in raw_paras:
                p = p.strip()
                if not p: continue
                if len(current_bubble) < 10 or p.startswith('(') or p.startswith('（'):
                    current_bubble += (" " if current_bubble else "") + p
                else:
                    if current_bubble: merged_paras.append(current_bubble)
                    current_bubble = p
            if current_bubble: merged_paras.append(current_bubble)
            
            final_bubbles = []
            for b in merged_paras[:6]:
                for i, code in enumerate(code_blocks):
                    b = b.replace(f"[__CODE_BLOCK_{i}__]", code)
                final_bubbles.append(b.strip())
                
            if image_cq_code: final_bubbles.append(image_cq_code)
    
            if len(current_history) >= 100:
                from tasks.summary_handler import summarize_memory_async
                asyncio.create_task(summarize_memory_async())
    
            return reply_text, sticker_tags, final_bubbles
            
        except Exception as e:
            logger.error(f"❌ 主脑生成失败: {repr(e)}")
            raise e

brain = BotBrain()
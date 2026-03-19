# bot/brain.py
import re
import json
import asyncio
import urllib.parse
from datetime import datetime
from openai import AsyncOpenAI

from core.config import cfg
from core.logger import logger
from bot.memory_manager import memory_manager
from tasks.schedule_manager import schedule_manager
from bot.tools.sticker_manager import sticker_manager
from bot.tools.tool_manager import get_tool_prompt, execute_search

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
        client = self.get_client(cfg.get("summary_gateway", 1))
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = (
            f"你是一个无情的日程状态判断机器。请根据【当前时间】与【今日日程】，严格判断角色现在是否有空聊天。\n"
            f"【当前时间】：{current_time_str}\n"
            f"【今日日程】：\n{schedule_info if schedule_info else '暂无特别安排'}\n"
            f"【用户消息】：{combined_text}\n\n"
            f"严格输出规则：\n"
            f"1. 如果当前处于休息、娱乐、摸鱼、吃饭或无安排的【空闲】状态，请直接且仅输出两个英文字母：YES\n"
            f"2. 如果当前处于睡觉、上课、工作、开会等无法看手机的【忙碌】状态，请计算距离下一次有空还需要几小时(保留1位小数)，并严格按照此格式输出：NO|小时数 （例如：NO|2.5）\n"
            f"绝对禁止输出任何其他文字、分析过程或标点符号！"
        )
        try:
            resp = await client.chat.completions.create(
                model=cfg.get("summary_model"), 
                messages=[{"role": "user", "content": prompt}], 
                temperature=0.0, 
                max_tokens=20,
                timeout=30.0  
            )
            raw_ans = resp.choices[0].message.content
            ans = raw_ans.strip().upper() if raw_ans else "YES"
            
            if "NO" in ans:
                try:
                    delay_hours = float(re.search(r'\d+(\.\d+)?', ans).group())
                except Exception:
                    delay_hours = 1.0
                logger.info(f"🛑 裁判判定当前忙碌，将延迟 {delay_hours} 小时后回复。")
                return False, f"日程繁忙，延迟 {delay_hours} 小时", delay_hours
            else:
                return True, "当前空闲，允许秒回", 0.0
                
        except Exception as e:
            logger.error(f"⚠️ 裁判模块异常，降级放行: {repr(e)}")
            return True, "报错降级放行", 0.0

    async def generate_reply(self, current_history: list, system_prompt_addon: str):
        client = self.get_client(cfg.get("chat_gateway", 1))
        active_prompt_name = cfg.get("active_prompt", "default.txt")
        logger.info(f"🎭 引擎开始构思，协议: [{active_prompt_name}]")
        
        dynamic_prompt = await memory_manager.load_active_prompt() + f"\n\n【当前真实时间】：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"
        
        core_mem = await memory_manager.load_core_memory()
        if core_mem and "暂无核心" not in core_mem: dynamic_prompt += f"\n\n【核心记忆】\n{core_mem}"
        dynamic_prompt += f"\n\n【近期轨迹】\n{await schedule_manager.get_recent_table_md()}"
        
        daily_schedule = await schedule_manager.get_todays_schedule()
        if daily_schedule: 
            dynamic_prompt += f"\n\n【今日日记参考】\n{daily_schedule}"

        dynamic_prompt += "\n\n【绝对输出规则】：\n1. 严格处于当前真实时间，禁预知未来！\n2. 聊天必须简短，最多不超过4句话！"
        dynamic_prompt += "\n\n【特殊内置指令】：如果达成约定，输出 `[RECORD_PROMISE: 事件]` ！"
        dynamic_prompt += await sticker_manager.get_system_prompt_addon()
        dynamic_prompt += get_tool_prompt() + system_prompt_addon

        messages = [{"role": "system", "content": dynamic_prompt}] + current_history

        try:
            response = await client.chat.completions.create(
                model=cfg.get("chat_model"), 
                messages=messages, 
                temperature=0.7,
                timeout=120.0
            )
            
            raw_reply = response.choices[0].message.content
            reply_text = raw_reply if raw_reply else "..."
    
            # 🌟 核心修复：引入 While 循环，支持一次聊天中发起多次查询/多维检索（最多允许深挖3次防止死循环）
            search_depth = 0
            while search_depth < 3:
                search_match = re.search(r'\[SEARCH:\s*(.*?)\]', reply_text)
                if not search_match:
                    break
                    
                search_query = search_match.group(1).strip()
                logger.info(f"🔍 [主脑工具调用] 正在搜索: {search_query}")
                search_result = await execute_search(search_query)
                
                messages.extend([
                    {"role": "assistant", "content": reply_text}, 
                    {"role": "system", "content": f"关于 '{search_query}' 的搜索结果:\n{search_result}\n\n请根据结果直接回答，不要重复触发该 SEARCH。"}
                ])
                
                response = await client.chat.completions.create(
                    model=cfg.get("chat_model"), 
                    messages=messages, 
                    temperature=0.7,
                    timeout=120.0
                )
                raw_reply_2 = response.choices[0].message.content
                reply_text = raw_reply_2 if raw_reply_2 else "..."
                search_depth += 1
    
            promise_matches = re.findall(r'\[RECORD_PROMISE:\s*(.*?)\]', reply_text)
            for promise in promise_matches:
                await schedule_manager.add_promise(promise)
                
            clean_reply = re.sub(r'\[RECORD_PROMISE:.*?\]', '', reply_text).strip()
            sticker_tags = re.findall(r'\[表情包:(.*?)\]', clean_reply)
            clean_reply = re.sub(r'\[表情包:.*?\]', '', clean_reply).strip()
            clean_reply = re.sub(r'\[\d{2}-\d{2}\s\d{2}:\d{2}\]\s*', '', clean_reply).strip()
            clean_reply = re.sub(r'\[SEARCH:.*?\]', '', clean_reply).strip()
            
            clean_reply = re.sub(r'\[PHOTO_GENERATION_PROMPT:.*?\]', '', clean_reply, flags=re.IGNORECASE|re.DOTALL).strip()
            clean_reply = re.sub(r'\[IMAGE:.*?\]', '', clean_reply, flags=re.IGNORECASE|re.DOTALL).strip()
            clean_reply = re.sub(r'\[视觉能力触发\]|\[发送照片\]|\[系统提示.*?\]', '', clean_reply).strip()
            
            image_cq_code = ""
            try:
                judge_client = self.get_client(cfg.get("summary_gateway", 1))
                image_judge_prompt = f"""你是一个配图裁判。
【AI准备发送的回复】：{reply_text}
如果回复同意发照片，输出独立一行: [IMAGE: 画面主体描述, 穿搭细节, 环境, 摄影风格]
如果不符合，只输出: [NO]"""
                
                judge_resp = await judge_client.chat.completions.create(
                    model=cfg.get("summary_model"),
                    messages=[{"role": "user", "content": image_judge_prompt}],
                    temperature=0.3,
                    timeout=30.0
                )
                raw_judge_content = judge_resp.choices[0].message.content
                judge_ans = raw_judge_content.strip() if raw_judge_content else "[NO]"
                
                img_match = re.search(r'\[IMAGE:\s*(.*?)\]', judge_ans)
                if img_match:
                    from bot.tools.image_generator import image_generator
                    image_cq_code = await image_generator.generate_life_photo(img_match.group(1).strip())
            except Exception as e:
                logger.error(f"⚠️ [配图裁判] 异常: {e}")
            
            # 注：打断施法前，已经将完整的原始构思写入了记忆，这样下次 AI 依然知道自己刚刚其实想完整表达什么，符合人类自然对话逻辑
            await memory_manager.append_memory("assistant", f"[{datetime.now().strftime('%m-%d %H:%M')}] {clean_reply}")
    
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
            
            final_bubbles = merged_paras[:6]
            if image_cq_code: final_bubbles.append(image_cq_code)
    
            if len(current_history) >= 100:
                from tasks.summary_handler import summarize_memory_async
                asyncio.create_task(summarize_memory_async())
    
            return reply_text, sticker_tags, final_bubbles
            
        except Exception as e:
            logger.error(f"❌ 主脑生成文本时遭遇故障: {repr(e)}")
            raise e

brain = BotBrain()
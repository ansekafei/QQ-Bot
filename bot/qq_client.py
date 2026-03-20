# bot/qq_client.py
import asyncio
import json
import re
import websockets
import hashlib
import time
from datetime import datetime

from core.config import cfg
from core.logger import logger
from bot.brain import brain
from bot.memory_manager import memory_manager
from bot.vision_handler import analyze_qq_image
from tasks.proactive_manager import proactive_manager
from bot.tools.sticker_manager import sticker_manager

user_buffers = {}
ws_connection = None
last_msg_cache = {}

async def send_qq_msg(target_id: str, text: str, msg_type: str):
    global ws_connection
    # 🌟 折中修复 5：短效防断连与防积压。等待 9 秒，连不上再丢弃。
    if not ws_connection:
        logger.warning(f"⚠️ WebSocket 暂未连接，挂起等待 3 秒尝试抢救发送至 [{target_id}]...")
        for _ in range(3):
            await asyncio.sleep(3)
            if ws_connection: break
        if not ws_connection:
            logger.error("❌ WebSocket 彻底断连，丢弃该消息以防积压成灾。")
            return
        
    action = "send_group_msg" if msg_type == 'group' else "send_private_msg"
    try:
        numeric_id = int(target_id)
    except ValueError:
        return

    payload = {
        "action": action,
        "params": {"group_id": numeric_id, "message": text} if msg_type == 'group' else {"user_id": numeric_id, "message": text},
        "echo": "reply"
    }
    try:
        await ws_connection.send(json.dumps(payload))
        logger.info(f"📤 气泡推流 -> [{target_id}] 内容: {text[:50]}...")
    except Exception as e:
        logger.error(f"❌ WebSocket 发送崩溃: {e}")

async def process_buffer(session_id: str, user_id: str, msg_type: str, target_id: str):
    try:
        timeout = cfg.get("listen_timeout", 8.0)
        await asyncio.sleep(timeout)
    except asyncio.CancelledError:
        return
    
    buffer_data = user_buffers.pop(session_id, None)
    if not buffer_data or not buffer_data['texts']: 
        return
        
    texts = buffer_data['texts']
    # 🌟 折中修复 3：加入年份，解决跨年失忆问题
    time_stamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
    context_prefix = "(在群聊中) " if msg_type == 'group' else ""
    
    if len(texts) > 1:
        logger.info(f"[{session_id}] ⏳ 连发 {len(texts)} 条消息，合并处理...")
        combined_text = "\n".join([f"[{i+1}] {t}" for i, t in enumerate(texts)])
        final_history_text = f"{time_stamp} {context_prefix}(连续发送了{len(texts)}条消息):\n{combined_text}"
        raw_combined = " ".join(texts)
    else:
        final_history_text = f"{time_stamp} {context_prefix}{texts[0]}"
        raw_combined = texts[0]

    if cfg.get("judge_enabled", True):
        should_reply, reason, delay_hours = await brain.judge_should_reply(raw_combined, "今日日程")
        if not should_reply:
            logger.info(f"[{session_id}] 🛑 裁判判定静默。原因: {reason}")
            await memory_manager.append_memory("user", final_history_text)
            if delay_hours > 0:
                proactive_manager.set_custom_proactive_delay(delay_hours)
            else:
                proactive_manager.update_interaction_time()
            return
            
    logger.info(f"[{session_id}] 🟢 裁判放行，请求主脑计算回复...")
    current_history = await memory_manager.append_memory("user", final_history_text)
    
    try:
        reply, sticker_tags, final_bubbles = await brain.generate_reply(current_history, "")
        
        for i, para in enumerate(final_bubbles):
            if session_id in user_buffers:
                logger.warning(f"[{session_id}] ⚠️ 气泡输出被用户新消息打断！剩余气泡取消。")
                break
                
            clean_para_for_length = re.sub(r'\[CQ:.*?\]', '', para)
            typing_time = min(len(clean_para_for_length) * 0.35, 10.0)
            
            interrupted = False
            for _ in range(int(typing_time / 0.5)):
                if session_id in user_buffers:
                    interrupted = True
                    break
                await asyncio.sleep(0.5)
                
            if not interrupted and (typing_time % 0.5) > 0:
                await asyncio.sleep(typing_time % 0.5)
                if session_id in user_buffers: interrupted = True
                
            if interrupted: break

            await send_qq_msg(target_id, para, msg_type)
            
            if i < len(final_bubbles) - 1:
                interrupted = False
                for _ in range(4): # 间隔 2.0s
                    if session_id in user_buffers:
                        interrupted = True
                        break
                    await asyncio.sleep(0.5)
                if interrupted: break

        if session_id not in user_buffers:
            for tag in sticker_tags:
                cq_sticker = await sticker_manager.get_sticker_id(tag)
                if cq_sticker:
                    await asyncio.sleep(2.5)
                    await send_qq_msg(target_id, cq_sticker, msg_type)
                    logger.info(f"✅ 发送QQ表情包: [{tag}]")
        
        proactive_manager.update_interaction_time()
        
    except Exception as e:
        logger.error(f"❌ 处理缓冲消息失败: {e}")
        proactive_manager.update_interaction_time()

async def handle_incoming_message(msg: dict):
    if msg.get("post_type") != "message": return
        
    msg_type = msg.get("message_type")
    user_id = str(msg.get("user_id"))
    text = msg.get("raw_message", "").strip()
    
    if not text: return
        
    if re.search(r'^[\【\[<&#91;]*(自动回复|不在电脑前|机器人)[\】\]>&#93;]*', text, re.IGNORECASE): return

    current_time = time.time()
    msg_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    cache_key = f"{user_id}_{msg_hash}"
    if cache_key in last_msg_cache and current_time - last_msg_cache[cache_key] < 3.0: return
    last_msg_cache[cache_key] = current_time
    expired_keys = [k for k, v in last_msg_cache.items() if current_time - v > 60]
    for k in expired_keys: del last_msg_cache[k]
        
    image_match = re.search(r'\[CQ:image,(.*?)\]', text)
    if image_match:
        attrs = image_match.group(1)
        url_match = re.search(r'url=(https?://[^,\]]+)', attrs)
        if url_match:
            image_url = url_match.group(1)
            file_match = re.search(r'file=([^,\]]+)', attrs)
            file_id = file_match.group(1) if file_match else None
            user_text = re.sub(r'\[CQ:image.*?\]', '', text).strip()
            text = await analyze_qq_image(image_url, user_text, file_id)

    allowed_users = cfg.get("allowed_users", "").split(",")
    allowed_groups = cfg.get("allowed_groups", "").split(",")
    if msg_type == "private" and allowed_users[0] and user_id not in allowed_users: return
    if msg_type == "group":
        group_id = str(msg.get("group_id"))
        if allowed_groups[0] == "0" or (allowed_groups[0] and group_id not in allowed_groups): return

    target_id = str(msg.get("group_id")) if msg_type == 'group' else user_id
    session_id = f"{msg_type}_{target_id}"

    if session_id in user_buffers:
        user_buffers[session_id]['texts'].append(text)
        if not user_buffers[session_id]['task'].done():
            user_buffers[session_id]['task'].cancel()
    else:
        user_buffers[session_id] = {'texts': [text]}
        
    user_buffers[session_id]['task'] = asyncio.create_task(
        process_buffer(session_id, user_id, msg_type, target_id)
    )

async def start_bot():
    global ws_connection
    while True:
        ws_url = cfg.get("cq_ws_url", "ws://napcat:3001")
        token = cfg.get("cq_token", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with websockets.connect(ws_url, extra_headers=headers) as ws:
                ws_connection = ws
                logger.info("✅ WebSocket 已连接 NapCatQQ。")
                async for message in ws:
                    try:
                        data = json.loads(message)
                        if "post_type" in data:
                            asyncio.create_task(handle_incoming_message(data))
                    except json.JSONDecodeError: pass
            ws_connection = None
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"❌ WebSocket 异常: {e}，5秒后重试...")
            ws_connection = None
            await asyncio.sleep(5)
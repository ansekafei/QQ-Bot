# bot/qq_client.py
import asyncio
import json
import re
import websockets
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

async def send_qq_msg(target_id: str, text: str, msg_type: str):
    if not ws_connection:
        logger.error("❌ WebSocket 未连接，无法发送消息！")
        return
        
    action = "send_group_msg" if msg_type == 'group' else "send_private_msg"
    try:
        numeric_id = int(target_id)
    except ValueError:
        logger.error(f"❌ 非法目标 ID，已阻断: {target_id}")
        return

    payload = {
        "action": action,
        "params": {"group_id": numeric_id, "message": text} if msg_type == 'group' else {"user_id": numeric_id, "message": text},
        "echo": "reply"
    }
    try:
        await ws_connection.send(json.dumps(payload))
        logger.info(f"📤 气泡推流 -> [{target_id}] 内容: {text}")
    except Exception as e:
        logger.error(f"❌ WebSocket 发送消息底层崩溃: {e}")

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
    time_stamp = datetime.now().strftime("[%m-%d %H:%M]")
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
            typing_time = min(len(para) * 0.35, 10.0)
            await asyncio.sleep(typing_time)
            await send_qq_msg(target_id, para, msg_type)
            if i < len(final_bubbles) - 1:
                await asyncio.sleep(2.0)

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
    if msg.get("post_type") != "message": 
        return
        
    msg_type = msg.get("message_type")
    user_id = str(msg.get("user_id"))
    text = msg.get("raw_message", "").strip()
    
    if not text: 
        return
        
    # 🌟 核心修复：死循环克星！直接在最外层拦截 QQ 自动回复
    if text.startswith("[自动回复]") or text.startswith("&#91;自动回复&#93;"):
        logger.warning(f"🚫 拦截到来自 {user_id} 的自动回复，已丢弃，防止死循环导致 AI 崩溃。")
        return
        
    image_match = re.search(r'\[CQ:image,(.*?)\]', text)
    if image_match:
        attrs = image_match.group(1)
        url_match = re.search(r'url=(https?://[^,\]]+)', attrs)
        file_match = re.search(r'file=([^,\]]+)', attrs)
        
        if url_match:
            image_url = url_match.group(1)
            file_id = file_match.group(1) if file_match else None
            user_text = re.sub(r'\[CQ:image.*?\]', '', text).strip()
            logger.info("🖼️ 拦截到图片消息，正在提交给视觉引擎分析...")
            text = await analyze_qq_image(image_url, user_text, file_id)

    logger.info(f"📩 [{msg_type}] {user_id}: {text[:50]}")
    
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
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"❌ WebSocket 连接断开或异常: {e}，10秒后重试...")
            ws_connection = None
            await asyncio.sleep(10)
# bot/vision_handler.py
import base64
import httpx
import re
import html
import urllib.parse
from core.config import cfg
from core.logger import logger
from bot.tools.sticker_manager import sticker_manager

async def analyze_qq_image(image_url: str, user_text: str, file_id: str = None) -> str:
    if not image_url:
        return user_text
        
    clean_image_url = html.unescape(image_url.split(',')[0].strip())
        
    vision_model_name = cfg.get("vision_model")
    
    vision_gateway = int(cfg.get("vision_gateway", 1))
    if vision_gateway == 2:
        api_key = cfg.get("api_key_2", "")
        base_url = cfg.get("base_url_2", "")
    else:
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "")
        
    proxy = cfg.get("global_proxy") or None
    
    if base_url:
        base_url = base_url.strip().rstrip('/')
        
    # 🌟 智能绕过内网代理黑洞
    actual_proxy = proxy
    if proxy and base_url:
        hostname = urllib.parse.urlparse(base_url).hostname or ""
        if '.' not in hostname or hostname in ['localhost', '127.0.0.1'] or hostname.startswith(('192.168.', '10.', '172.')):
            actual_proxy = None
    
    try:
        # 下载图片需要外网环境，用全局 proxy
        logger.info(f"📥 [视觉引擎] 正在从腾讯 CDN 下载图片数据...")
        async with httpx.AsyncClient(timeout=15.0, proxy=proxy) as http_client:
            resp = await http_client.get(clean_image_url)
            
            if resp.status_code != 200:
                logger.error(f"❌ [视觉引擎] 图片下载失败！HTTP状态码: {resp.status_code}")
                return f"【系统提示：我发了一张图片，但 Bot 无法下载它 (HTTP {resp.status_code})】"
                
            file_bytes = resp.content

        raw_content_type = resp.headers.get('Content-Type', '')
        clean_content_type = raw_content_type.split(';')[0].strip().lower()
        if clean_content_type not in ['image/jpeg', 'image/png', 'image/webp', 'image/gif']:
            clean_content_type = 'image/jpeg'

        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        logger.info(f"📸 [视觉引擎] 图片抓取完毕, 大小: {len(file_bytes)/1024:.2f} KB。正在使用网关[{vision_gateway}]组装大模型请求...")
        
        vision_prompt = (
            "请用幽默、拟人化、甚至带点吐槽的语气来描述这张图片或表情包。如果是带有文字的表情包，请把文字也读出来。\n"
            "【核心任务】：请务必判断这张图是“普通的实拍照片/风景/截图”，还是一张“表情包(Meme/梗图)”？\n"
            "如果你认为这是一张可以被收藏的表情包，请务必在你的回复最末尾独立一行输出：`[STICKER:情绪]`，情绪只能从【开心、难过、贴贴、生气】这四个词中选一个（选最贴近的）。\n"
            "如果这只是一般照片，绝对不要输出这个标签！"
        )
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{clean_content_type};base64,{base64_image}"}}
                ]
            }
        ]
        
        # 访问网关用绕过后的 actual_proxy
        logger.info(f"🚀 [视觉引擎] 请求已发往大模型网关，正在等待上游响应 (最高等待 180 秒，请耐心)...")
        async with httpx.AsyncClient(timeout=180.0, proxy=actual_proxy) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": vision_model_name, "messages": messages, "temperature": 0.7}
            )
            
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code} - {response.text}")
                
            res_data = response.json()
            if 'choices' not in res_data or not res_data['choices']:
                raise ValueError(f"API 返回数据异常: {res_data}")
                
            message_data = res_data['choices'][0].get('message', {})
            description = message_data.get('content')
            if description is None:
                raise ValueError(f"模型未返回文本，原始 message: {message_data}")
            description = description.strip()
            
        description = re.sub(r'<think>.*?</think>', '', description, flags=re.DOTALL).strip()
        
        logger.info(f"✅ [视觉引擎] 网关响应成功！正在分析标签...")
        sticker_match = re.search(r'\[STICKER:(.*?)\]', description)
        if sticker_match:
            emotion = sticker_match.group(1).strip()
            description = description.replace(sticker_match.group(0), '').strip()
            
            if file_id and emotion in ["开心", "难过", "贴贴", "生气"]:
                cq_code = f"[CQ:image,file={file_id}]"
                try:
                    await sticker_manager.add_sticker(emotion, cq_code, clean_image_url)
                    logger.info(f"🌟 检测到表情包！已自动收录至图鉴库: 分类 [{emotion}]")
                except Exception as e:
                    logger.error(f"❌ 保存表情包时出错: {e}")

        if not description: description = "一张无法用语言描述的图片"
        final_text = f"【系统提示：我发送了一张图片/表情包，视觉系统识别到的内容是：“{description}”】"
        if user_text: final_text += f"\n我说：{user_text}"
        return final_text
        
    except httpx.TimeoutException:
        error_msg = "请求网关/大模型超时 (超过130秒)，上游渠道严重拥堵或宕机。"
        logger.error(f"❌ [视觉引擎] 失败: {error_msg}")
        fallback_text = f"【系统提示：我发送了一张图片，但是视觉系统等了太久超时了。】"
        if user_text: fallback_text += f"\n我说：{user_text}"
        return fallback_text
        
    except Exception as e:
        error_msg = repr(e)
        logger.error(f"❌ [视觉引擎] 失败: {error_msg}")
        fallback_text = f"【系统提示：我发送了一张图片，视觉系统出错了。错误信息：{error_msg}】"
        if user_text: fallback_text += f"\n我说：{user_text}"
        return fallback_text
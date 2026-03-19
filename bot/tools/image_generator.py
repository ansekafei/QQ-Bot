# bot/tools/image_generator.py
import httpx
import urllib.parse
import os
from core.logger import logger
from core.config import cfg

class ImageGenerator:
    async def generate_life_photo(self, description: str) -> str:
        gen_gateway = int(cfg.get("image_gateway", 1))
        edit_gateway = int(cfg.get("image_edit_gateway", 1))
        
        def get_creds(gw_idx):
            if gw_idx == 2:
                return cfg.get("base_url_2", "").rstrip('/'), cfg.get("api_key_2", "")
            return cfg.get("base_url", "").rstrip('/'), cfg.get("api_key", "")
            
        gen_base, gen_key = get_creds(gen_gateway)
        edit_base, edit_key = get_creds(edit_gateway)
        
        gen_model = cfg.get("image_model", "grok-imagine-1.0")
        edit_model = cfg.get("image_edit_model", "grok-imagine-1.0-edit")
        proxy = cfg.get("global_proxy") or None

        def get_actual_proxy(url):
            if not proxy: return None
            hostname = urllib.parse.urlparse(url).hostname or ""
            if '.' not in hostname or hostname in ['localhost', '127.0.0.1'] or hostname.startswith(('192.168.', '10.', '172.')):
                return None
            return proxy

        gen_proxy = get_actual_proxy(gen_base)
        edit_proxy = get_actual_proxy(edit_base)

        # 🌟 核心：注入你提供的“极致真实感”二次精修提示词
        realistic_refine_prompt = (
            "将图片中的人物转化为极具真实感的真人。建立一张看起来像是用 iPhone 自拍或随手拍摄的照片。"
            "照片中不应有刻意清晰的主体或完美的构图，而应是一张随意、无意识的日常快照。"
            "照片应因轻微移动而略带模糊，光影（如路灯或自然光）均匀且真实。宽高比呈现为 9:16 的视觉感。"
            "照片绝对不能看起来像是人工智能生成的，必须呈现出 100% 真人拍摄的生活质感。"
        )

        try:
            logger.info(f"🎨 [视觉输出] 开始构思生活照: {description}")
            
            # 检测本地是否有固定角色参考图 (垫图)
            ref_image_path = None
            if os.path.exists("data/ref_image.png"):
                ref_image_path = "data/ref_image.png"
            elif os.path.exists("data/ref_image.jpg"):
                ref_image_path = "data/ref_image.jpg"
                
            if ref_image_path:
                logger.info(f"🎨 [视觉输出] 发现本地角色参考图 [{ref_image_path}]，启用【图生图·双重精修】暴爽模式...")
                with open(ref_image_path, "rb") as f:
                    base_image_bytes = f.read()
                    
                async with httpx.AsyncClient(timeout=60.0, proxy=edit_proxy) as client_edit:
                    # ================= 垫图模式 - 阶段 1：场景变换 =================
                    logger.info(f"🎨 [视觉输出] 垫图阶段 1/2: 根据聊天上下文重绘场景与动作...")
                    edit1_payload = {
                        "model": edit_model,
                        "prompt": f"请严格保持参考图中人物的五官特征、气质和基础设定，将其置入以下生活场景中，并根据场景调整动作与服装：{description}",
                        "n": 1,
                        "size": "1024x1024"
                    }
                    files1 = {"image": ("image.png", base_image_bytes, "image/png")}
                    
                    edit1_resp = await client_edit.post(
                        f"{edit_base}/images/edits",
                        headers={"Authorization": f"Bearer {edit_key}"},
                        data=edit1_payload,
                        files=files1
                    )
                    if edit1_resp.status_code >= 400:
                        raise Exception(f"垫图阶段1报错 HTTP {edit1_resp.status_code}: {edit1_resp.text}")
                    
                    mid_image_url = edit1_resp.json()["data"][0]["url"]
                    final_image_url = mid_image_url # 保底
                    
                    # ================= 垫图模式 - 阶段 2：iPhone质感精修 =================
                    try:
                        logger.info(f"🎨 [视觉输出] 垫图阶段 2/2: 使用 iPhone 随拍质感提示词进行二次精修...")
                        # 下载阶段 1 换好场景的图
                        async with httpx.AsyncClient(timeout=30.0, proxy=proxy) as dl_client:
                            mid_img_resp = await dl_client.get(mid_image_url)
                            mid_img_resp.raise_for_status()
                            
                        edit2_payload = {
                            "model": edit_model,
                            "prompt": realistic_refine_prompt,
                            "n": 1,
                            "size": "1024x1024"
                        }
                        files2 = {"image": ("image.png", mid_img_resp.content, "image/png")}
                        
                        edit2_resp = await client_edit.post(
                            f"{edit_base}/images/edits",
                            headers={"Authorization": f"Bearer {edit_key}"},
                            data=edit2_payload,
                            files=files2
                        )
                        if edit2_resp.status_code >= 400:
                            raise Exception(f"垫图阶段2报错 HTTP {edit2_resp.status_code}: {edit2_resp.text}")
                            
                        final_image_url = edit2_resp.json()["data"][0]["url"]
                        logger.info("✅ [视觉输出] 垫图双重精修处理完毕，iPhone 质感注入成功！")
                    except Exception as edit2_err:
                        logger.warning(f"⚠️ [视觉输出] 垫图阶段 2 (二次精修) 失败，已降级返回阶段 1 初稿。原因: {repr(edit2_err)}")

                    return f"[CQ:image,file={final_image_url},summary=一张生活照]"

            # ================= 以下为没有参考图时的原版双阶段生成 =================
            # 【阶段 1】：生成初稿
            async with httpx.AsyncClient(timeout=60.0, proxy=gen_proxy) as client_gen:
                logger.info(f"🎨 [视觉输出] 无参考图阶段 1/2: 使用 {gen_model} 凭空生成初稿...")
                gen_payload = {
                    "model": gen_model,
                    "prompt": f"一张照片。人物细节：{description}",
                    "n": 1,
                    "size": "1024x1024"
                }
                gen_resp = await client_gen.post(
                    f"{gen_base}/images/generations",
                    headers={"Authorization": f"Bearer {gen_key}"},
                    json=gen_payload
                )
                if gen_resp.status_code >= 400:
                    raise Exception(f"阶段1生图失败 HTTP {gen_resp.status_code}: {gen_resp.text}")
                initial_image_url = gen_resp.json()["data"][0]["url"]
                
            # 【阶段 2】：尝试精修细节
            final_image_url = initial_image_url
            try:
                logger.info(f"🎨 [视觉输出] 无参考图阶段 2/2: 使用 iPhone 随拍质感提示词尝试精修细节...")
                
                async with httpx.AsyncClient(timeout=30.0, proxy=proxy) as dl_client:
                    img_resp = await dl_client.get(initial_image_url)
                    img_resp.raise_for_status()
                
                async with httpx.AsyncClient(timeout=60.0, proxy=edit_proxy) as client_edit:
                    edit_payload = {
                        "model": edit_model,
                        "prompt": realistic_refine_prompt,
                        "n": 1,
                        "size": "1024x1024"
                    }
                    files = {"image": ("image.png", img_resp.content, "image/png")}
                    
                    edit_resp = await client_edit.post(
                        f"{edit_base}/images/edits",
                        headers={"Authorization": f"Bearer {edit_key}"},
                        data=edit_payload,
                        files=files
                    )
                    if edit_resp.status_code >= 400:
                        raise Exception(f"精修接口报错 HTTP {edit_resp.status_code}: {edit_resp.text}")
                    final_image_url = edit_resp.json()["data"][0]["url"]
                    logger.info("✅ [视觉输出] 生活照双阶段处理完毕！")
                    
            except Exception as edit_err:
                logger.warning(f"⚠️ [视觉输出] 阶段 2 (精修) 失败，已降级返回初稿。原因: {repr(edit_err)}")
        
            return f"[CQ:image,file={final_image_url},summary=一张生活照]"
            
        except Exception as e:
            logger.error(f"❌ [视觉输出] 照片生成彻底失败，已被装甲隔离: {repr(e)}")
            return ""

image_generator = ImageGenerator()
# bot/tools/sticker_manager.py
import os
import random
from core.file_io import async_read_json, async_write_json
from core.logger import logger

STICKER_FILE = "data/stickers.json"

class StickerManager:
    async def load_stickers(self) -> dict:
        default_template = {"开心": [], "难过": [], "贴贴": [], "生气": []}
        data = await async_read_json(STICKER_FILE, default=default_template)
        # 如果文件为空或者读取出错，回退到默认
        if not data:
            data = default_template
            await async_write_json(STICKER_FILE, data)
        return data

    # 🌟 修改：接收真实的文件ID和图片URL，而不是以前的 file_id_with_emoji
    async def add_sticker(self, emotion: str, file_id: str, image_url: str):
        stickers = await self.load_stickers()
        if emotion not in stickers:
            stickers[emotion] = []
            
        # 查重：防止同一个表情包被重复保存
        for existing in stickers[emotion]:
            if existing.startswith(file_id + "|"):
                return
                
        # 拼接成 file_id|url 的格式，前端 WebUI 发现是 http 开头就会自动渲染图片
        item_string = f"{file_id}|{image_url}"
        stickers[emotion].append(item_string)
        await async_write_json(STICKER_FILE, stickers)

    async def remove_sticker(self, emotion: str, item_string: str):
        stickers = await self.load_stickers()
        if emotion in stickers and item_string in stickers[emotion]:
            stickers[emotion].remove(item_string)
            if not stickers[emotion]:
                del stickers[emotion]
            await async_write_json(STICKER_FILE, stickers)

    async def get_sticker_id(self, emotion: str) -> str:
        stickers = await self.load_stickers()
        if emotion in stickers and stickers[emotion]:
            choice = random.choice(stickers[emotion])
            # 以 | 分割，取出最前面的 file_id 给 NapCatQQ 发送
            return choice.split('|')[0]
        return None

    async def get_system_prompt_addon(self) -> str:
        stickers = await self.load_stickers()
        emotions = [emo for emo, ids in stickers.items() if ids]
        if not emotions:
            return ""
        
        emotion_str = ", ".join(emotions)
        roll_chance = random.randint(0, 100)
        logger.info(f"🎲 [表情图鉴] Roll 点抽奖，本次发送表情概率为: {roll_chance}%")
        
        return (
            f"\n\n【表情包图鉴库】：当前可用表情分类有：[{emotion_str}]。"
            f"⚠️ 动态概率约束：本次回复附带表情包几率为 {roll_chance}%。"
            f"请参考概率决定是否发送表情包。如果要发，请加上形如 `[表情包:情绪]` 的标签。"
        )

sticker_manager = StickerManager()
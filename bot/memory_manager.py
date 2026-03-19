# bot/memory_manager.py
import os
import json
import shutil
import asyncio
from datetime import datetime

from core.config import cfg
from core.file_io import async_read_text, async_write_text
from core.logger import logger

class MemoryManager:
    def __init__(self):
        # 🌟 核心修复：引入异步读写锁，防止高频聊天时记忆文件读写冲突导致丢包
        self._lock = asyncio.Lock()
        
    def _get_char_dir(self, char_name=None):
        active_char = str(char_name) if char_name else str(cfg.get("active_prompt", "default"))
        active_char = active_char.replace(".txt", "")
        char_dir = os.path.join("data", "prompts", active_char)
        os.makedirs(char_dir, exist_ok=True)
        return char_dir

    def _get_file_paths(self, char_name=None):
        char_dir = self._get_char_dir(char_name)
        core_file = os.path.join(char_dir, "memory_core.txt")
        long_file = os.path.join(char_dir, "memory_long.txt")
        short_file = os.path.join(char_dir, "memory_short.json")
        self._ensure_migrated(char_dir, core_file, long_file, short_file)
        return core_file, long_file, short_file

    def _ensure_migrated(self, char_dir, core_file, long_file, short_file):
        marker = os.path.join(char_dir, ".migrated")
        if os.path.exists(marker): return

        prompt_file = os.path.join(char_dir, "prompt.txt")
        old_prompt_file = os.path.join("data", "prompts", f"{os.path.basename(char_dir)}.txt")
        
        if not os.path.exists(prompt_file) and os.path.exists(old_prompt_file):
            try: shutil.move(old_prompt_file, prompt_file)
            except Exception: pass
            
        old_core = "data/core_memory.txt"
        old_short = "data/short_term/history.json"
        
        if not os.path.exists(core_file) and os.path.exists(old_core):
            try: shutil.move(old_core, core_file)
            except Exception: pass
        if not os.path.exists(short_file) and os.path.exists(old_short):
            try: shutil.move(old_short, short_file)
            except Exception: pass

        try:
            with open(marker, "w") as f: f.write("ok")
        except Exception: pass

    async def load_active_prompt(self, char_name=None):
        char_dir = self._get_char_dir(char_name)
        prompt_file = os.path.join(char_dir, "prompt.txt")
        self._get_file_paths(char_name)
        return await async_read_text(prompt_file, default="【系统指令】\n请在此输入新角色的设定...\n")

    async def load_core_memory(self, char_name=None):
        core_file, _, _ = self._get_file_paths(char_name)
        return await async_read_text(core_file, default="暂无核心记忆。")

    async def save_core_memory(self, text: str, char_name=None):
        core_file, _, _ = self._get_file_paths(char_name)
        await async_write_text(core_file, text)

    async def load_history(self, char_name=None):
        _, _, short_file = self._get_file_paths(char_name)
        try:
            content = await async_read_text(short_file, default="[]")
            return json.loads(content)
        except Exception:
            return []

    async def save_history(self, history_list: list, char_name=None):
        _, _, short_file = self._get_file_paths(char_name)
        await async_write_text(short_file, json.dumps(history_list, ensure_ascii=False, indent=4))

    async def append_memory(self, role: str, content: str, char_name=None):
        async with self._lock:  # 保护读写过程
            history = await self.load_history(char_name)
            history.append({"role": role, "content": content})
            if len(history) > 120:
                history = history[-120:]
            await self.save_history(history, char_name)
            return history

memory_manager = MemoryManager()
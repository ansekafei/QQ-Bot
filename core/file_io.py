# core/file_io.py
import os
import json
import asyncio
import aiofiles

# 全局异步锁，按文件路径分配锁，避免阻塞无关文件的读写
_file_locks = {}

def get_lock(filepath: str) -> asyncio.Lock:
    if filepath not in _file_locks:
        _file_locks[filepath] = asyncio.Lock()
    return _file_locks[filepath]

async def async_read_json(filepath: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    
    lock = get_lock(filepath)
    async with lock:
        try:
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else default
        except Exception as e:
            print(f"⚠️ 读取 JSON 失败 {filepath}: {e}")
            return default

async def async_write_json(filepath: str, data: dict):
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    lock = get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

async def async_read_text(filepath: str, default: str = ""):
    if not os.path.exists(filepath):
        return default
    lock = get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
            return await f.read()

async def async_write_text(filepath: str, text: str, mode: str = 'w'):
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    lock = get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, mode, encoding='utf-8') as f:
            await f.write(text)
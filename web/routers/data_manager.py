# web/routers/data_manager.py
import os
import json
import shutil
from fastapi import APIRouter, Request

from core.config import cfg
from core.file_io import async_read_text, async_write_text
from bot.memory_manager import memory_manager
from tasks.schedule_manager import schedule_manager
from bot.tools.sticker_manager import sticker_manager
from tasks.summary_handler import summarize_memory_async

router = APIRouter()
PROMPTS_DIR = "data/prompts"

# ----- 日程与表情图鉴 -----
@router.get("/schedule_data")
async def get_schedule_data(): 
    return {"diary": await schedule_manager.get_todays_schedule(), "history": await schedule_manager.load_history()}

@router.post("/trigger_schedule")
async def trigger_schedule():
    result = await schedule_manager.generate_daily_schedule(force=True)
    return {"status": "success", "msg": "记忆生成成功" if result else "生成失败"}

@router.post("/trigger_clean_promises")
async def trigger_clean_promises():
    try: return {"status": "success", "msg": (await schedule_manager.clean_outdated_promises())[1]}
    except Exception as e: return {"status": "error", "msg": str(e)}

@router.get("/stickers_data")
async def get_stickers_data(): 
    return await sticker_manager.load_stickers()

@router.post("/delete_sticker")
async def delete_sticker_endpoint(request: Request):
    data = await request.json()
    await sticker_manager.remove_sticker(data.get('emotion'), data.get('file_id'))
    return {"status": "success"}

# 🌟 新增：批量删除表情包接口
@router.post("/delete_stickers_batch")
async def delete_stickers_batch_endpoint(request: Request):
    data = await request.json()
    items = data.get('items', [])
    for item in items:
        await sticker_manager.remove_sticker(item.get('emotion'), item.get('file_id'))
    return {"status": "success"}

# ----- 记忆管理 -----
@router.api_route("/memory_data", methods=["GET", "POST"])
async def get_memory_data(request: Request):
    try:
        char_name = None
        if request.method == "POST":
            try:
                data = await request.json()
                char_name = data.get('char_name')
            except Exception:
                pass
                
        _, long_file, _ = memory_manager._get_file_paths(char_name)
        return {
            "core": await memory_manager.load_core_memory(char_name), 
            "short": json.dumps(await memory_manager.load_history(char_name), ensure_ascii=False, indent=4), 
            "long": await async_read_text(long_file, default="暂无长期记忆归档。")
        }
    except Exception as e:
        return {
            "core": f"【系统内部读取错误】: {str(e)}", 
            "short": "[]", 
            "long": f"【系统内部读取错误】: {str(e)}"
        }

@router.post("/set_core_memory")
async def set_core_memory(request: Request):
    data = await request.json()
    await memory_manager.save_core_memory(data.get('memory', ''), data.get('char_name'))
    return {"status": "success"}

@router.post("/set_memory")
async def set_memory(request: Request):
    data = await request.json()
    try: 
        await memory_manager.save_history(json.loads(data.get('memory', '[]')), data.get('char_name'))
        return {"status": "success"}
    except Exception as e: 
        return {"status": "error", "msg": str(e)}

@router.post("/clear_long_memory")
async def clear_long_memory(request: Request):
    data = await request.json()
    _, long_file, _ = memory_manager._get_file_paths(data.get('char_name'))
    await async_write_text(long_file, "=== 记忆归档档案 ===\n")
    return {"status": "success"}

@router.post("/trigger_summary")
async def trigger_summary(request: Request):
    char_name = (await request.json()).get('char_name')
    original_active = cfg.get("active_prompt")
    
    if char_name:
        await cfg.update(active_prompt=char_name)
        
    success, msg = await summarize_memory_async()
    
    if char_name:
        await cfg.update(active_prompt=original_active)
        
    return {"status": "success" if success else "error", "msg": msg}

# ----- 角色卡管理 -----
@router.get("/prompts_list")
async def get_prompts_list():
    try:
        os.makedirs(PROMPTS_DIR, exist_ok=True)
        dirs = [d for d in os.listdir(PROMPTS_DIR) if os.path.isdir(os.path.join(PROMPTS_DIR, d))]
        active = str(cfg.get("active_prompt", "default")).replace(".txt", "")
        
        if not dirs:
            os.makedirs(os.path.join(PROMPTS_DIR, "default"), exist_ok=True)
            dirs = ["default"]
            
        return {"active": active, "list": sorted(dirs)}
    except Exception as e:
        return {"active": "error", "list": [f"Error: {str(e)}"]}

@router.post("/read_prompt")
async def read_prompt(request: Request):
    filename = (await request.json()).get('filename', '')
    char_name = filename.replace(".txt", "") if filename else str(cfg.get("active_prompt", "default")).replace(".txt", "")
    path = os.path.join(PROMPTS_DIR, char_name, "prompt.txt")
    return {"content": await async_read_text(path, default="【系统指令】\n请在此输入新角色的设定...\n")}

@router.post("/set_active_prompt")
async def set_active_prompt(request: Request):
    filename = (await request.json()).get('filename', '')
    char_name = filename.replace(".txt", "")
    await cfg.update(active_prompt=char_name)
    return {"status": "success"}

@router.post("/set_prompt")
async def set_prompt(request: Request):
    data = await request.json()
    filename = data.get('filename', '')
    char_name = filename.replace(".txt", "") if filename else str(cfg.get("active_prompt", "default")).replace(".txt", "")
    
    char_dir = os.path.join(PROMPTS_DIR, char_name)
    os.makedirs(char_dir, exist_ok=True)
    path = os.path.join(char_dir, "prompt.txt")
    await async_write_text(path, data.get('prompt', ''))
    return {"status": "success"}

@router.post("/create_prompt")
async def create_prompt(request: Request):
    filename = (await request.json()).get('filename', '')
    char_name = filename.replace(".txt", "")
    if char_name:
        char_dir = os.path.join(PROMPTS_DIR, char_name)
        os.makedirs(char_dir, exist_ok=True)
        path = os.path.join(char_dir, "prompt.txt")
        if not os.path.exists(path): 
            await async_write_text(path, "【系统指令】\n请在此输入新角色的设定...\n")
    return {"status": "success"}

@router.post("/delete_prompt")
async def delete_prompt(request: Request):
    filename = (await request.json()).get('filename', '')
    char_name = filename.replace(".txt", "")
    if char_name and char_name != "default":
        char_dir = os.path.join(PROMPTS_DIR, char_name)
        if os.path.exists(char_dir):
            shutil.rmtree(char_dir)
    return {"status": "success"}
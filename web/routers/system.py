# web/routers/system.py
import os
import asyncio
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.config import cfg
from core.logger import LOG_FILE
from core.file_io import async_read_text

router = APIRouter()

@router.get("/logs")
async def get_logs():
    if not os.path.exists(LOG_FILE): return JSONResponse(content=[])
    try:
        content = await async_read_text(LOG_FILE)
        return JSONResponse(content=content.strip().split("\n")[-150:])
    except Exception: return JSONResponse(content=[])

@router.get("/env_data")
async def get_env_data():
    return {
        "API_KEY": cfg.get("api_key"), "BASE_URL": cfg.get("base_url"),
        "API_KEY_2": cfg.get("api_key_2"), "BASE_URL_2": cfg.get("base_url_2"),
        "CQ_WS_URL": cfg.get("cq_ws_url"), "CQ_TOKEN": cfg.get("cq_token"),
        "GIT_PROXY": cfg.get("git_proxy"), # 🌟 彻底重命名为 Git 专属代理
        "WEBUI_USERNAME": cfg.get("webui_username"), 
        "WEBUI_PASSWORD": cfg.get("webui_password"),
        "SERPAPI_KEY": cfg.get("serpapi_key"),
        "GITHUB_USERNAME": cfg.get("github_username"),
        "GITHUB_TOKEN": cfg.get("github_token"),
        "GITHUB_REPO": cfg.get("github_repo")
    }

@router.post("/set_env")
async def set_env(request: Request):
    data = await request.json()
    await cfg.update(
        api_key=data.get("API_KEY", ""), base_url=data.get("BASE_URL", ""),
        api_key_2=data.get("API_KEY_2", ""), base_url_2=data.get("BASE_URL_2", ""),
        cq_ws_url=data.get("CQ_WS_URL", ""), cq_token=data.get("CQ_TOKEN", ""),
        git_proxy=data.get("GIT_PROXY", ""), # 🌟 彻底重命名
        webui_username=data.get("WEBUI_USERNAME", ""), 
        webui_password=data.get("WEBUI_PASSWORD", ""),
        serpapi_key=data.get("SERPAPI_KEY", ""),
        github_username=data.get("GITHUB_USERNAME", ""),
        github_token=data.get("GITHUB_TOKEN", ""),
        github_repo=data.get("GITHUB_REPO", "")
    )
    return {"status": "success", "msg": "核心配置与密钥已分离并安全保存！"}

@router.post("/test_api")
async def test_api(request: Request):
    data = await request.json()
    gw = int(data.get('gateway', 1))
    
    if gw == 2:
        api = data.get('api_key_2', '').strip()
        base = data.get('base_url_2', '').strip().rstrip('/')
    else:
        api = data.get('api_key', '').strip()
        base = data.get('base_url', '').strip().rstrip('/')
        
    if not api or not base: return {"status": "error", "msg": "对应网关参数不能为空"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            res = await c.get(f"{base}/models", headers={"Authorization": f"Bearer {api}"})
            if res.status_code == 200:
                return {"status": "success", "msg": f"✅ 网关{gw}连接成功！获取到 {len(res.json().get('data', []))} 个模型"}
            return {"status": "error", "msg": f"❌ 连接异常！状态码: {res.status_code}"}
    except Exception as e:
        return {"status": "error", "msg": f"💀 错误: {str(e)}"}

@router.get("/models")
async def get_models():
    default_set = {cfg.get("chat_model"), cfg.get("summary_model"), cfg.get("vision_model"), cfg.get("image_model"), cfg.get("image_edit_model")}
    models_1 = default_set.copy()
    models_2 = default_set.copy()
    
    async def fetch_gw(api_key, base_url, target_set):
        if base_url: base_url = base_url.strip().rstrip('/')
        if api_key and base_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
                    if res.status_code == 200:
                        target_set.update([m["id"] for m in res.json().get("data", [])])
            except Exception: pass

    await asyncio.gather(
        fetch_gw(cfg.get("api_key"), cfg.get("base_url"), models_1),
        fetch_gw(cfg.get("api_key_2"), cfg.get("base_url_2"), models_2)
    )
        
    return {
        "chat_model": cfg.get("chat_model"), "chat_gateway": cfg.get("chat_gateway", 1),
        "summary_model": cfg.get("summary_model"), "summary_gateway": cfg.get("summary_gateway", 1),
        "vision_model": cfg.get("vision_model"), "vision_gateway": cfg.get("vision_gateway", 1),
        "image_model": cfg.get("image_model"), "image_gateway": cfg.get("image_gateway", 1),
        "image_edit_model": cfg.get("image_edit_model"), "image_edit_gateway": cfg.get("image_edit_gateway", 1),
        "models_1": sorted(list(models_1)),
        "models_2": sorted(list(models_2))
    }

@router.post("/set_model")
async def set_model(request: Request):
    data = await request.json()
    t, m, g = data.get('type'), data.get('model'), int(data.get('gateway', 1))
    
    if t == 'chat': await cfg.update(chat_model=m, chat_gateway=g)
    elif t == 'vision': await cfg.update(vision_model=m, vision_gateway=g)
    elif t == 'summary': await cfg.update(summary_model=m, summary_gateway=g)
    elif t == 'image': await cfg.update(image_model=m, image_gateway=g)
    elif t == 'image_edit': await cfg.update(image_edit_model=m, image_edit_gateway=g)
    
    return {"status": "success"}

@router.post("/restart")
async def handle_restart():
    asyncio.create_task(asyncio.sleep(1)).add_done_callback(lambda _: os._exit(42))
    return {"status": "success", "msg": "系统即将重启"}
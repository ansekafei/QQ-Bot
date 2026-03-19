from fastapi import APIRouter, Request
from core.config import cfg

router = APIRouter()

@router.get("/listen_targets")
async def get_listen_targets(): 
    return {"users": cfg.get("allowed_users"), "groups": cfg.get("allowed_groups")}

@router.post("/set_listen_targets")
async def set_listen_targets(request: Request):
    data = await request.json()
    await cfg.update(allowed_users=data.get('users', ''), allowed_groups=data.get('groups', ''))
    return {"status": "success"}

@router.get("/listen_config")
async def get_listen_config(): 
    return {"timeout": cfg.get("listen_timeout"), "judge_enabled": cfg.get("judge_enabled")}

@router.post("/set_listen_config")
async def set_listen_config(request: Request):
    data = await request.json()
    await cfg.update(listen_timeout=float(data.get('timeout', 8.0)), judge_enabled=data.get('judge_enabled', True))
    return {"status": "success"}

@router.get("/proactive_config")
async def get_proactive_config():
    return {
        "enabled": cfg.get("proactive_enabled"), "min_hours": cfg.get("proactive_min_hours"), "max_hours": cfg.get("proactive_max_hours"),
        "dnd_start": cfg.get("dnd_start_time"), "dnd_end": cfg.get("dnd_end_time")
    }

@router.post("/set_proactive_config")
async def set_proactive_config(request: Request):
    data = await request.json()
    await cfg.update(
        proactive_enabled=data.get('enabled', True), proactive_min_hours=float(data.get('min_hours', 8.0)), proactive_max_hours=float(data.get('max_hours', 16.0)),
        dnd_start_time=data.get('dnd_start', "23:00"), dnd_end_time=data.get('dnd_end', "08:00")
    )
    return {"status": "success"}
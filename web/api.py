# web/api.py
import base64
import secrets
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from core.file_io import async_read_text
from core.config import cfg

# 导入模块化拆分的路由
from web.routers import system, bot_core, data_manager, editor

class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 实时读取配置文件中的账号和密码
        expected_user = cfg.get("webui_username", "").strip()
        expected_pwd = cfg.get("webui_password", "").strip()
        
        # 如果账号和密码都留空，直接放行（免密模式）
        if not expected_user and not expected_pwd:
            return await call_next(request)
        
        # 检查请求头中是否包含 Authorization 字段
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return PlainTextResponse(
                "Unauthorized: 请输入正确的控制台账号与密码", 
                status_code=401, 
                headers={"WWW-Authenticate": 'Basic realm="AI WebUI Secure Area"'}
            )
        
        try:
            # 解析浏览器传来的 Basic Auth 凭证
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
            
            # 使用 secrets.compare_digest 防止时序攻击
            user_ok = secrets.compare_digest(username, expected_user) if expected_user else True
            pwd_ok = secrets.compare_digest(password, expected_pwd) if expected_pwd else True
            
            if not (user_ok and pwd_ok):
                return PlainTextResponse(
                    "Unauthorized: 账号或密码错误", 
                    status_code=401, 
                    headers={"WWW-Authenticate": 'Basic realm="AI WebUI Secure Area"'}
                )
        except Exception:
            return PlainTextResponse(
                "Unauthorized: 认证解析失败", 
                status_code=401, 
                headers={"WWW-Authenticate": 'Basic realm="AI WebUI Secure Area"'}
            )
            
        # 账号密码正确，放行请求
        return await call_next(request)

app = FastAPI(title="AI WebUI")

# 注册全局认证拦截器
app.add_middleware(BasicAuthMiddleware)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="web/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    content = await async_read_text("web/static/index.html", default="<h1>缺少 index.html</h1>")
    return HTMLResponse(content=content)

@app.get("/repair", response_class=HTMLResponse)
async def serve_repair():
    content = await async_read_text("web/static/repair.html", default="<h1>缺少 repair.html</h1>")
    return HTMLResponse(content=content)

# 将各个模块的 Router 注册到 FastAPI 实例中
app.include_router(system.router)
app.include_router(bot_core.router)
app.include_router(data_manager.router)
app.include_router(editor.router)
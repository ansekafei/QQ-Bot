# emergency_webui.py
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# 引入我们的纯净代码编辑器后端
from web.routers import editor

app = FastAPI(title="Emergency IDE")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 挂载文件编辑器路由
app.include_router(editor.router)

@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open("web/static/repair.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<h1>⚠️ 灾难：连 repair.html 都丢失了！</h1><p>报错: {e}</p>"

if __name__ == "__main__":
    print("🚨 灾难救援模式已启动！请访问 WebUI 端口修复代码。")
    # 通常绑定到 Docker 的 8080 内部端口
    uvicorn.run(app, host="0.0.0.0", port=8080)
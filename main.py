import asyncio
import signal
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from loguru import logger
from dotenv import set_key

from core.napcat_ws import NapCatWebSocket
from core.brain import Brain
from config.settings import settings

# 全局变量
ws_client: NapCatWebSocket = None
brain: Brain = None
ENV_FILE = ".env"  # 环境变量文件路径

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理"""
    logger.info("正在初始化 AI 女友系统...")
    
    global ws_client, brain
    ws_client = NapCatWebSocket()
    brain = Brain(send_callback=ws_client.send_message)
    ws_client.message_handler = brain.handle_message
    
    # 在启动 WebSocket 之前，显式地等待数据库初始化
    await brain.sqlite_db.init_db()
    
    ws_task = asyncio.create_task(ws_client.start())
    
    yield
    
    logger.info("正在关闭 AI 女友系统...")
    await ws_client.stop()
    ws_task.cancel()

app = FastAPI(title="AI 女友系统", lifespan=lifespan)

# ==========================================
# 🌟 WebUI 控制台 (参数可视化设置面板)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def web_ui():
    """返回配置面板 HTML"""
    
    # 1. 读取角色设定
    char_info = {}
    char_file = "bot/zhangqinxi/character.json"
    if os.path.exists(char_file):
        with open(char_file, "r", encoding="utf-8") as f:
            char_info = json.load(f)
            
    name = char_info.get("name", "张情兮")
    style = char_info.get("style", "")

    # 2. 读取系统环境变量 (直接从 settings 中获取当前加载的值)
    ws_url = settings.NAPCAT_WS_URL
    token = settings.NAPCAT_TOKEN
    api_base = settings.LLM_API_BASE
    api_key = settings.LLM_API_KEY

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI 控制台</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-50 text-slate-800 p-4 md:p-8 font-sans">
        <div class="max-w-4xl mx-auto space-y-6">
            
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex items-center justify-between">
                <h1 class="text-2xl font-bold text-indigo-600 flex items-center">
                    <span class="text-3xl mr-3">🧠</span> AI Core Controller
                </h1>
                <span class="px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-bold rounded border border-emerald-200">
                    🟢 服务运行中
                </span>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="font-bold text-slate-700 mb-4 flex items-center border-b pb-2">
                        <span class="mr-2">⚙️</span> 系统网络配置 (.env)
                    </h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-1">NapCat WebSocket 地址</label>
                            <input type="text" id="sys-ws" value="{ws_url}" class="w-full border border-slate-300 rounded p-2 text-sm font-mono focus:ring-2 focus:ring-indigo-300 outline-none" placeholder="ws://192.168.x.x:3001">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-1">NapCat Token</label>
                            <input type="password" id="sys-token" value="{token}" class="w-full border border-slate-300 rounded p-2 text-sm font-mono focus:ring-2 focus:ring-indigo-300 outline-none" placeholder="Bearer token">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-1">大模型 API Base (网
                                💾 保存系统配置 (需重启生效)
                            </button>
                        </div>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="font-bold text-slate-700 mb-4 flex items-center border-b pb-2">
                        <span class="mr-2">🎭</span> 角色设定 (character.json)
                    </h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-1">AI 称呼 (Name)</label>
                            <input type="text" id="char-name" value="{name}" class="w-full border border-slate-300 rounded p-2 text-sm focus:ring-2 focus:ring-pink-300 outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-1">说话风格 (Style)</label>
                            <textarea id="char-style" rows="4" class="w-full border border-slate-300 rounded p-2 text-sm focus:ring-2 focus:ring-pink-300 outline-none resize-none">{style}</textarea>
                        </div>
                        <div class="pt-2">
                            <button onclick="saveCharacterConfig()" id="btn-char" class="w-full py-2 bg-pink-500 hover:bg-pink-600 text-white text-sm font-bold rounded shadow transition-colors">
                                💖 保存角色设定 (即时生效)
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="toast" class="fixed bottom-10 left-1/2 transform -translate-x-1/2 hidden px-6 py-3 rounded shadow-lg text-sm font-bold z-50 transition-opacity duration-300"></div>
        </div>

        <script>
            function showToast(msg, isWarning = false) {{
                const toast = document.getElementById('toast');
                toast.innerText = msg;
                toast.className = `fixed bottom-10 left-1/2 transform -translate-x-1/2 px-6 py-3 rounded shadow-xl text-sm font-bold z-50 transition-opacity duration-300 ${{isWarning ? 'bg-amber-100 text-amber-800 border border-amber-300' : 'bg-emerald-100 text-emerald-800 border border-emerald-300'}}`;
                toast.classList.remove('hidden');
                setTimeout(() => toast.classList.add('hidden'), 4000);
            }}

            async function saveSystemConfig() {{
                const btn = document.getElementById('btn-sys');
                btn.innerText = '⏳ 保存中...';
                btn.disabled = true;
                
                const payload = {{
                    napcat_ws_url: document.getElementById('sys-ws').value.trim(),
                    llm_api_base: document.getElementById('sys-api-base').value.trim(),
                    llm_api_key: document.getElementById('sys-api-key').value.trim()
                }};
                
                try {{
                    const res = await fetch('/api/config/system', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(payload)
                    }});
                    const data = await res.json();
                    if (data.status === 'success') {{
                        showToast('✅ 系统配置已保存！请在 Loader 面板点击【🔄 重启】以建立新连接。', true);
                    }} else {{
                        showToast('❌ 保存失败: ' + data.message, true);
                    }}
                }} catch (e) {{
                    showToast('❌ 网络请求失败', true);
                }} finally {{
                    btn.innerText = '💾 保存系统配置 (需重启生效)';
                    btn.disabled = false;
                }}
            }}

            async function saveCharacterConfig() {{
                const btn = document.getElementById('btn-char');
                btn.innerText = '⏳ 保存中...';
                btn.disabled = true;
                
                const payload = {{
                    name: document.getElementById('char-name').value.trim(),
                    style: document.getElementById('char-style').value.trim()
                }};
                
                try {{
                    const res = await fetch('/api/config/character', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(payload)
                    }});
                    const data = await res.json();
                    if (data.status === 'success') showToast('✅ 角色设定已更新！即时生效。');
                }} catch (e) {{
                    showToast('❌ 保存失败', true);
                }} finally {{
                    btn.innerText = '💖 保存角色设定 (即时生效)';
                    btn.disabled = false;
                }}
            }}
        </script>
    </body>
    </html>
    """
    return html_content


# ==========================================
# 🔌 WebUI 专用的 API 接口
# ==========================================

@app.post("/api/config/system")
async def update_system_config(request: Request):
    """修改 .env 环境变量文件"""
    data = await request.json()
    
    # 确保 .env 文件存在
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, 'a').close()
        
    try:
        if "napcat_ws_url" in data:
            set_key(ENV_FILE, "NAPCAT_WS_URL", data["napcat_ws_url"])
        if "llm_api_base" in data:
            set_key(ENV_FILE, "LLM_API_BASE", data["llm_api_base"])
        if "llm_api_key" in data:
            set_key(ENV_FILE, "LLM_API_KEY", data["llm_api_key"])
            
        logger.info("系统环境变量已被 WebUI 更新，等待重启生效。")
        return {"status": "success", "message": "配置已保存入 .env"}
    except Exception as e:
        logger.error(f"写入 .env 失败: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/config/character")
async def update_character_config(request: Request):
    """修改 character.json 角色设定"""
    data = await request.json()
    char_file = "bot/zhangqinxi/character.json"
    
    if os.path.exists(char_file):
        try:
            with open(char_file, "r", encoding="utf-8") as f:
                char_info = json.load(f)
                
            char_info["name"] = data.get("name", char_info.get("name"))
            char_info["style"] = data.get("style", char_info.get("style"))
            
            with open(char_file, "w", encoding="utf-8") as f:
                json.dump(char_info, f, ensure_ascii=False, indent=2)
                
            return {"status": "success", "message": "角色配置已更新"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
            
    return {"status": "error", "message": "找不到 character.json 配置文件"}


def signal_handler(signum, frame):
    logger.info(f"接收到信号 {signum}，正在关闭应用...")
    if ws_client:
        asyncio.create_task(ws_client.stop())
    exit(0)


if __name__ == "__main__":
    import uvicorn
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 动态获取 Loader 注入的内部端口
    port = int(os.environ.get("PORT", 8000))
    
    logger.info("启动 AI 女友系统...")
    logger.info(f"API 服务将在 http://0.0.0.0:{port} 上运行")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
# web/routers/editor.py
import os
import subprocess
from fastapi import APIRouter, Request
from core.config import cfg
from core.file_io import async_read_text, async_write_text
from core.logger import logger

router = APIRouter()

def get_base_dir():
    return os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

@router.get("/files_list")
async def get_files_list():
    base_dir = get_base_dir()
    file_list = []
    for root, dirs, files in os.walk(base_dir):
        if '.git' in root or '__pycache__' in root or 'napcat_data' in root: continue
        for f in files:
            if os.path.splitext(f)[1] in {'.py', '.html', '.json', '.txt', '.yml', '.js', '.css'} or f in ['Dockerfile', '.gitignore', '.env']:
                file_list.append(os.path.relpath(os.path.join(root, f), base_dir).replace('\\', '/')) 
    return {"files": sorted(file_list)}

@router.post("/read_file")
async def read_file(request: Request):
    base_dir = get_base_dir()
    safe_path = os.path.abspath(os.path.join(base_dir, (await request.json()).get('filename', '')))
    if safe_path.startswith(base_dir) and os.path.exists(safe_path): return {"status": "success", "content": await async_read_text(safe_path)}
    return {"status": "error", "msg": "文件不存在或越权访问"}

@router.post("/save_file")
async def save_file(request: Request):
    data = await request.json()
    base_dir = get_base_dir()
    safe_path = os.path.abspath(os.path.join(base_dir, data.get('filename', '')))
    if safe_path.startswith(base_dir): 
        await async_write_text(safe_path, data.get('content', ''))
        return {"status": "success", "msg": "保存成功"}
    return {"status": "error", "msg": "非法文件路径"}

@router.post("/create_file")
async def create_file(request: Request):
    filename = (await request.json()).get('filename', '').strip()
    if not filename: return {"status": "error", "msg": "文件名不能为空"}
    base_dir = get_base_dir()
    safe_path = os.path.abspath(os.path.join(base_dir, filename))
    if not safe_path.startswith(base_dir): return {"status": "error", "msg": "非法文件路径"}
    if os.path.exists(safe_path): return {"status": "error", "msg": "文件或同名目录已存在"}
    try: 
        await async_write_text(safe_path, "")
        return {"status": "success", "msg": "文件创建成功"}
    except Exception as e: 
        return {"status": "error", "msg": f"创建失败: {str(e)}"}

# ==================== Git 灾备核心逻辑 ====================

def _get_git_env_and_urls(base_dir):
    gh_user = cfg.get("github_username", "").strip()
    gh_token = cfg.get("github_token", "").strip()
    gh_repo = cfg.get("github_repo", "").strip()
    
    if not all([gh_user, gh_token, gh_repo]):
        return None, None, None, {"status": "error", "msg": "❌ 请在配置面板填齐 GitHub 用户名、密钥和仓库路径！"}
        
    clean_repo = gh_repo.replace("https://github.com/", "").replace("github.com/", "")
    if clean_repo.endswith(".git"): clean_repo = clean_repo[:-4]
    
    real_url = f"https://{gh_user}:{gh_token}@github.com/{clean_repo}.git"
    safe_url = f"https://{gh_user}:***@github.com/{clean_repo}.git"
    
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"

    proxy = cfg.get("git_proxy", "").strip()
    if proxy:
        env["http_proxy"] = proxy; env["https_proxy"] = proxy; env["ALL_PROXY"] = proxy
        subprocess.run(f'git config --global http.proxy {proxy} && git config --global https.proxy {proxy}', cwd=base_dir, shell=True)
    else:
        subprocess.run('git config --global --unset http.proxy && git config --global --unset https.proxy', cwd=base_dir, shell=True)
        
    subprocess.run('git config --global user.email "bot@local" && git config --global user.name "WebUI-Bot"', cwd=base_dir, shell=True, env=env)
    return env, real_url, safe_url, None

@router.post("/git_push")
async def git_push(request: Request):
    base_dir = get_base_dir()
    env, real_url, safe_url, err_resp = _get_git_env_and_urls(base_dir)
    if err_resp: return err_resp

    try: commit_msg = (await request.json()).get("commit_message", "").strip()
    except: commit_msg = ""
    if not commit_msg: commit_msg = "Auto backup from WebUI"
        
    try:
        logger.info(f"☁️ [同步迭代版 main] 提交更改: {commit_msg}")
        cmd_set_remote = f'git remote set-url origin {real_url} || git remote add origin {real_url}'
        subprocess.run(cmd_set_remote, cwd=base_dir, shell=True, env=env)
        
        # 🌟 核心修改：在 push origin main 后面加上了 -f (force) 暴力强推参数！
        cmd_push = f'git branch -M main && git add . && (git diff-index --quiet HEAD || git commit -m "{commit_msg}") && git push origin main -f'
        
        result = subprocess.run(cmd_push, cwd=base_dir, shell=True, capture_output=True, text=True, timeout=60, env=env)
        
        if result.returncode == 0:
            logger.info("✅ [同步成功] 已同步至 main 分支！")
            return {"status": "success", "msg": "✅ 迭代代码已成功同步至云端 main 分支！"}
        else:
            safe_err = result.stderr.replace(real_url, safe_url)
            logger.error(f"❌ [同步报错] \n{safe_err}")
            return {"status": "error", "msg": "❌ 推送失败！详细日志请查看控制台！\n" + safe_err[:500]}
    except Exception as e:
        safe_e = str(e).replace(real_url, safe_url)
        logger.error(f"❌ [Git崩溃] {safe_e}")
        return {"status": "error", "msg": f"执行异常: {safe_e}"}

@router.post("/git_publish_stable")
async def git_publish_stable():
    base_dir = get_base_dir()
    env, real_url, safe_url, err_resp = _get_git_env_and_urls(base_dir)
    if err_resp: return err_resp

    try:
        logger.info(f"🏷️ [发布稳定版 stable] 正在将当前代码永久标记归档...")
        cmd_set_remote = f'git remote set-url origin {real_url} || git remote add origin {real_url}'
        subprocess.run(cmd_set_remote, cwd=base_dir, shell=True, env=env)
        
        cmd_push_stable = f'git branch -M main && git add . && (git diff-index --quiet HEAD || git commit -m "Auto Tag Stable") && git push origin main:stable -f'
        result = subprocess.run(cmd_push_stable, cwd=base_dir, shell=True, capture_output=True, text=True, timeout=60, env=env)
        
        if result.returncode == 0:
            logger.info("✅ [发布成功] 当前代码已归档至云端 stable 分支！")
            return {"status": "success", "msg": "✅ 完美！当前版本已被永久存档在云端的 stable 分支！"}
        else:
            safe_err = result.stderr.replace(real_url, safe_url)
            logger.error(f"❌ [发布报错] \n{safe_err}")
            return {"status": "error", "msg": "❌ 发布失败！\n" + safe_err[:500]}
    except Exception as e:
        safe_e = str(e).replace(real_url, safe_url)
        return {"status": "error", "msg": f"执行异常: {safe_e}"}

@router.post("/git_restore_stable")
async def git_restore_stable():
    base_dir = get_base_dir()
    env, real_url, safe_url, err_resp = _get_git_env_and_urls(base_dir)
    if err_resp: return err_resp

    try:
        logger.warning(f"⏪ [灾难恢复] 正在从云端拉取 stable 稳定分支进行降维覆盖...")
        cmd_set_remote = f'git remote set-url origin {real_url} || git remote add origin {real_url}'
        subprocess.run(cmd_set_remote, cwd=base_dir, shell=True, env=env)
        
        cmd_restore = f'git fetch origin stable && git reset --hard origin/stable && git clean -fd'
        result = subprocess.run(cmd_restore, cwd=base_dir, shell=True, capture_output=True, text=True, timeout=60, env=env)
        
        if result.returncode == 0:
            logger.warning("✅ [恢复完成] 本地代码已被强制还原为云端 stable 存档！")
            return {"status": "success", "msg": "⏪ 已强制拉取并洗牌为 stable 稳定版！\n建议您立即热重启以加载旧版代码。"}
        else:
            safe_err = result.stderr.replace(real_url, safe_url)
            logger.error(f"❌ [恢复报错] \n{safe_err}")
            return {"status": "error", "msg": "❌ 恢复失败！(云端可能还没有 stable 分支，请先发布一次)\n" + safe_err[:500]}
    except Exception as e:
        safe_e = str(e).replace(real_url, safe_url)
        return {"status": "error", "msg": f"执行异常: {safe_e}"}

@router.post("/git_rollback")
async def git_rollback():
    base_dir = get_base_dir()
    try:
        logger.warning("⏪ [本地撤销] 正在回退到上一次的本地提交状态...")
        cmd = 'git reset --hard HEAD~1 && git clean -fd'
        result = subprocess.run(cmd, cwd=base_dir, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0: return {"status": "success", "msg": "⏪ 已丢弃未提交更改，并回退至本地上个版本！"}
        else: return {"status": "error", "msg": "❌ 回滚失败：\n" + result.stderr}
    except Exception as e:
        return {"status": "error", "msg": f"执行异常: {str(e)}"}
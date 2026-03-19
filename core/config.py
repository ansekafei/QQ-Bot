# core/config.py
import os
import json
import asyncio
from core.file_io import async_read_text, async_write_text

CONFIG_FILE = "data/config.json"
ENV_FILE = ".env"

# 定义哪些键属于敏感/环境变量（将被自动隔离到 .env 文件中，防止 git 泄露）
ENV_KEYS = {
    "api_key", "base_url", "api_key_2", "base_url_2",
    "cq_ws_url", "cq_token", "git_proxy",
    "webui_username", "webui_password", "serpapi_key",
    "github_username", "github_token", "github_repo"
}

class ConfigManager:
    def __init__(self):
        self._data = {}
        self._env_data = {}
        self._lock = asyncio.Lock()
        self._sync_load()

    def _sync_load(self):
        # 1. 加载非敏感配置文件 (config.json)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        
        # 2. 加载敏感环境变量文件 (.env)
        if os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            self._env_data[k.strip().lower()] = v.strip().strip("'").strip('"')
            except Exception:
                pass

        # 3. 无缝升级与自动迁移：剥离敏感数据到 .env
        migrated = False
        
        if "global_proxy" in self._data:
            self._env_data["git_proxy"] = self._data.pop("global_proxy")
            migrated = True
        
        for k in list(self._data.keys()):
            if k.lower() in ENV_KEYS:
                self._env_data[k.lower()] = self._data.pop(k)
                migrated = True
        
        # 4. 纠正 .txt 后缀遗留问题
        if "active_prompt" in self._data and self._data["active_prompt"].endswith(".txt"):
            self._data["active_prompt"] = self._data["active_prompt"].replace(".txt", "")
            migrated = True
            
        # 如果发生了迁移，立即分别覆盖保存两个文件
        if migrated:
            self._sync_save_both()

    def _sync_save_both(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        
        try:
            lines = [f"{k.upper()}={v}" for k, v in self._env_data.items()]
            with open(ENV_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    # 🌟 核心修复：加回一个空壳 load 方法，兼容 main.py 的调用！
    async def load(self):
        pass

    def get(self, key, default=None):
        key_lower = key.lower()
        # 优先从 .env 或系统环境变量读取敏感数据
        if key_lower in ENV_KEYS:
            env_val = os.environ.get(key_lower.upper())
            if env_val is not None:
                return env_val
            return self._env_data.get(key_lower, default)
        
        # 非敏感数据从 config.json 读取
        return self._data.get(key_lower, default)

    async def update(self, **kwargs):
        async with self._lock:
            config_changed = False
            env_changed = False
            
            for k, v in kwargs.items():
                key_lower = k.lower()
                if key_lower in ENV_KEYS:
                    if self._env_data.get(key_lower) != v:
                        self._env_data[key_lower] = v
                        env_changed = True
                else:
                    if self._data.get(key_lower) != v:
                        self._data[key_lower] = v
                        config_changed = True
            
            if config_changed:
                await async_write_text(CONFIG_FILE, json.dumps(self._data, ensure_ascii=False, indent=4))
            
            if env_changed:
                lines = [f"{k.upper()}={v}" for k, v in self._env_data.items()]
                await async_write_text(ENV_FILE, "\n".join(lines) + "\n")

cfg = ConfigManager()
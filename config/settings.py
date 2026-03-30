import os
from dotenv import load_dotenv

# 加载根目录的 .env 文件
load_dotenv()

class Settings:
    """全局配置类"""
    
    # LLM 配置
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    # NapCat WebSocket 配置
    NAPCAT_WS_URL: str = os.getenv("NAPCAT_WS_URL", "ws://localhost:3000/ws")
    NAPCAT_TOKEN: str = os.getenv("NAPCAT_TOKEN", "")
    
    # 防抖配置
    DEBOUNCE_DELAY: float = float(os.getenv("DEBOUNCE_DELAY", "4.0"))  # 消息防抖延迟时间（秒）
    
    # 重连配置
    RECONNECT_DELAY: float = float(os.getenv("RECONNECT_DELAY", "5.0"))  # 重连延迟时间（秒）
    MAX_RECONNECT_ATTEMPTS: int = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "10"))  # 最大重连次数
    
    # 内存配置
    SHORT_TERM_MEMORY_SIZE: int = int(os.getenv("SHORT_TERM_MEMORY_SIZE", "100"))  # 短期记忆最大条数
    SUMMARIZE_THRESHOLD: int = int(os.getenv("SUMMARIZE_THRESHOLD", "90"))  # 满百归十的阈值
    
    # 向量检索配置
    TOP_K: int = int(os.getenv("TOP_K", "5"))  # 向量检索返回的最相似条目数

# 全局配置实例
settings = Settings()

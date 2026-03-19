# bot/tools/tool_manager.py
import httpx
import json
import os
import time
import hashlib
from core.config import cfg
from core.logger import logger
from core.file_io import async_read_text, async_write_text

CACHE_DIR = "/tmp/bot/search_cache"
CACHE_EXPIRY_DAYS = 7
CACHE_EXPIRY_SECONDS = CACHE_EXPIRY_DAYS * 24 * 3600

def _get_cache_path(query: str) -> str:
    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"{query_hash}.json")

def _clean_old_cache():
    if not os.path.exists(CACHE_DIR): return
    current_time = time.time()
    for filename in os.listdir(CACHE_DIR):
        filepath = os.path.join(CACHE_DIR, filename)
        if os.path.isfile(filepath):
            if current_time - os.path.getmtime(filepath) > CACHE_EXPIRY_SECONDS:
                try: os.remove(filepath)
                except Exception: pass

def get_tool_prompt() -> str:
    return (
        "\n\n【搜索引擎能力】：如果用户询问了客观事实、实时新闻、天气或者你不知道的知识，你可以输出 `[SEARCH:你要搜索的关键词]`。系统会自动为你检索并把结果返回给你。"
        "\n⚠️ 极其重要的生存警告：系统的搜索结果会固定缓存 7 天！如果你要查询【今天的天气】、【今天的新闻】等对时间极其敏感的时效性内容，你必须在搜索关键词中强行加入当前日期！（例如：`[SEARCH:2026年3月20日 南京天气]`），否则你查到的永远是几天前的过期信息！"
    )

async def execute_search(query: str, ignore_limit=False) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    _clean_old_cache()

    cache_path = _get_cache_path(query)
    
    if os.path.exists(cache_path):
        try:
            cache_content = await async_read_text(cache_path)
            if cache_content:
                cache_data = json.loads(cache_content)
                if time.time() - cache_data.get('timestamp', 0) < CACHE_EXPIRY_SECONDS:
                    logger.info(f"🔍 [联网搜索] ⚡ 命中本地 7 天缓存，为您省下一次 API 调用: {query}")
                    return cache_data.get('result_text', "未找到相关有用信息。")
        except Exception as e:
            logger.warning(f"⚠️ 读取搜索缓存失败: {e}")

    api_key = cfg.get("serpapi_key")
    if not api_key:
        logger.warning("未配置 SerpApi 密钥，搜索请求被拒绝。")
        return "【系统提示：未配置搜索引擎 API，无法联网查阅。请根据你自己的知识回答，或者告诉用户你现在无法联网。】"
    
    logger.info(f"🔍 [联网搜索] 🌐 正在通过 API 全网检索: {query}")
    
    try:
        # 🌟 核心修改：移除 proxy 传入，直接通过 NAS 网络直连 SerpApi
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params={
                "q": query, "api_key": api_key, "engine": "google", "hl": "zh-cn", "gl": "cn"
            })
            if resp.status_code != 200:
                logger.debug(f"❌ [联网搜索失败] HTTP状态码: {resp.status_code}")
                return f"【系统提示：搜索失败，状态码 {resp.status_code}。请直接回答或向用户道歉。】"
            
            data = resp.json()
            snippets = []
            if "answer_box" in data and "answer" in data["answer_box"]: snippets.append(f"答案盒子: {data['answer_box']['answer']}")
            elif "answer_box" in data and "snippet" in data["answer_box"]: snippets.append(f"答案盒子: {data['answer_box']['snippet']}")
                
            if "organic_results" in data:
                for idx, res in enumerate(data["organic_results"][:3]):
                    snippet = res.get("snippet", "")
                    if snippet: snippets.append(f"结果{idx+1}: {snippet}")
                    
            result_text = "\n".join(snippets) if snippets else "未找到相关有用信息。"
            final_result = f"【系统搜索结果】：\n{result_text}"

            try:
                cache_json = json.dumps({"timestamp": time.time(), "query": query, "result_text": final_result}, ensure_ascii=False, indent=2)
                await async_write_text(cache_path, cache_json)
            except Exception: pass

            return final_result
            
    except Exception as e:
        logger.error(f"❌ 搜索异常: {e}")
        return "【系统提示：搜索引擎网络异常，请直接回答或向用户道歉。】"
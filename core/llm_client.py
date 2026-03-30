import httpx
import asyncio
from typing import List, Dict, Any
from loguru import logger

from config.settings import settings


class LLMClient:
    """LLM 客户端：API 熔断与调度"""
    
    def __init__(self):
        """初始化 LLM 客户端"""
        self.api_base = settings.LLM_API_BASE
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        
        # 创建 httpx 异步客户端
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),  # 30秒超时，连接超时10秒
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的向量嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 向量嵌入
        """
        url = f"{self.api_base}/embeddings"
        
        try:
            response = await self.client.post(
                url,
                json={
                    "input": text,
                    "model": "text-embedding-ada-002"  # 默认使用这个嵌入模型
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 提取嵌入向量
            embedding = result["data"][0]["embedding"]
            return embedding
            
        except httpx.TimeoutException:
            logger.error("获取嵌入向量时超时")
            return await self._get_fallback_embedding(text)
        except httpx.HTTPStatusError as e:
            logger.error(f"获取嵌入向量时发生HTTP错误: {e}")
            return await self._get_fallback_embedding(text)
        except Exception as e:
            logger.error(f"获取嵌入向量时发生异常: {e}")
            return await self._get_fallback_embedding(text)
    
    async def generate_chat(self, messages: List[Dict[str, str]]) -> str:
        """
        生成聊天回复
        
        Args:
            messages: 对话消息列表，每个消息包含 role 和 content
            
        Returns:
            str: AI生成的回复
        """
        url = f"{self.api_base}/chat/completions"
        
        try:
            response = await self.client.post(
                url,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 提取AI回复
            ai_response = result["choices"][0]["message"]["content"]
            return ai_response
            
        except httpx.TimeoutException:
            logger.error("生成聊天回复时超时")
            return await self._get_fallback_response()
        except httpx.HTTPStatusError as e:
            logger.error(f"生成聊天回复时发生HTTP错误: {e}")
            return await self._get_fallback_response()
        except Exception as e:
            logger.error(f"生成聊天回复时发生异常: {e}")
            return await self._get_fallback_response()
    
    async def _get_fallback_embedding(self, text: str) -> List[float]:
        """
        获取备用嵌入向量（当API失败时的兜底方案）
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 随机或零向量作为备用
        """
        # 这里返回一个简单的零向量作为备用方案
        # 在实际应用中，可能需要一个更复杂的备用方案
        return [0.0] * 1536  # 假设使用1536维的嵌入向量
    
    async def _get_fallback_response(self) -> str:
        """
        获取备用响应（当API失败时的兜底方案）
        
        Returns:
            str: 备用响应文本
        """
        fallback_responses = [
            "抱歉，我现在有点忙，稍后再回复你。",
            "我正在处理一些事情，暂时无法回复。",
            "网络似乎有点问题，我们稍后再聊吧。",
            "我需要一点时间思考，稍后回复你。"
        ]
        
        # 随机选择一个备用响应
        import random
        return random.choice(fallback_responses)
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()
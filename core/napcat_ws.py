import asyncio
import json
import websockets
from typing import Dict, List, Optional, Callable
from loguru import logger

from config.settings import settings


class NapCatWebSocket:
    """NapCat WebSocket 通信层：实现防抖与断线重连机制"""
    
    def __init__(self, message_handler: Callable = None):
        """
        初始化 WebSocket 客户端
        
        Args:
            message_handler: 消息处理回调函数
        """
        self.ws_url = settings.NAPCAT_WS_URL
        self.message_handler = message_handler
        self.websocket = None
        self.running = False
        
        # 消息防抖相关
        self.message_buffer: Dict[str, List[str]] = {}  # 用户消息缓冲区
        self.debounce_timers: Dict[str, asyncio.TimerHandle] = {}  # 防抖计时器
        self.debounce_delay = settings.DEBOUNCE_DELAY
        
    async def connect(self):
        """连接到 NapCat WebSocket 服务器"""
        reconnect_attempts = 0
        
        while self.running and reconnect_attempts < settings.MAX_RECONNECT_ATTEMPTS:
            try:
                logger.info(f"正在连接到 NapCat WebSocket: {self.ws_url}")
                # 为 WebSocket 连接添加鉴权 Header
                headers = {"User-Agent": "AI-Girlfriend-Client/1.0"}
                if settings.NAPCAT_TOKEN:
                    headers["Authorization"] = f"Bearer {settings.NAPCAT_TOKEN}"
                self.websocket = await websockets.connect(
                    self.ws_url,
                    extra_headers=headers
                )
                logger.success("成功连接到 NapCat WebSocket")
                
                # 重置重连尝试次数
                reconnect_attempts = 0
                
                # 启动消息接收循环
                await self._message_loop()
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket 连接已关闭，尝试重连...")
                await self._handle_disconnect()
            except Exception as e:
                logger.error(f"WebSocket 连接异常: {e}")
                await self._handle_disconnect()
            
            # 重连延迟
            reconnect_attempts += 1
            if self.running and reconnect_attempts < settings.MAX_RECONNECT_ATTEMPTS:
                logger.info(f"等待 {settings.RECONNECT_DELAY} 秒后进行第 {reconnect_attempts} 次重连尝试...")
                await asyncio.sleep(settings.RECONNECT_DELAY)
        
        if reconnect_attempts >= settings.MAX_RECONNECT_ATTEMPTS:
            logger.error("达到最大重连尝试次数，停止重连")
    
    async def _handle_disconnect(self):
        """处理连接断开"""
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None
        
        # 取消所有防抖计时器
        for timer in self.debounce_timers.values():
            timer.cancel()
        self.debounce_timers.clear()
        self.message_buffer.clear()
    
    async def _message_loop(self):
        """消息接收循环"""
        async for message in self.websocket:
            try:
                data = json.loads(message)
                await self._handle_incoming_message(data)
            except json.JSONDecodeError:
                logger.error(f"无法解析接收到的消息: {message}")
            except Exception as e:
                logger.error(f"处理消息时发生异常: {e}")
    
    async def _handle_incoming_message(self, data: dict):
        """处理接收到的消息"""
        # 根据 OneBot V11 协议判断事件类型
        post_type = data.get("post_type", "")
        
        if post_type == "message":
            # 提取消息信息 - OneBot V11 中的字段
            message_type = data.get("message_type", "")
            if message_type == "private":
                # 私聊消息
                user_id = str(data.get("user_id", ""))
                raw_message = data.get("raw_message", "")
            elif message_type == "group":
                # 群消息
                user_id = f"group_{data.get('group_id', '')}_{data.get('user_id', '')}"
                raw_message = data.get("raw_message", "")
            else:
                # 其他消息类型
                user_id = str(data.get("user_id", ""))
                raw_message = data.get("raw_message", "")
            
            if user_id and raw_message:
                await self._add_message_to_buffer(user_id, raw_message)
        elif post_type == "request":
            # 处理好友请求
            request_type = data.get("request_type", "")
            if request_type == "friend":
                logger.info(f"收到好友请求: {data}")
            elif request_type == "group":
                logger.info(f"收到群请求: {data}")
        elif post_type == "notice":
            # 处理系统通知
            logger.info(f"收到系统通知: {data}")
        elif post_type == "meta_event":
            # 过滤心跳包等元事件，不记录日志防止刷屏
            pass
        else:
            logger.debug(f"收到其他类型事件: {data.get('post_type')}")
    
    async def _add_message_to_buffer(self, user_id: str, message: str):
        """将消息添加到缓冲区并启动防抖计时器"""
        # 初始化用户消息缓冲区
        if user_id not in self.message_buffer:
            self.message_buffer[user_id] = []
        
        # 添加消息到缓冲区
        self.message_buffer[user_id].append(message)
        logger.debug(f"消息已添加到用户 {user_id} 的缓冲区: {message}")
        
        # 如果已有该用户的计时器，取消它
        if user_id in self.debounce_timers:
            self.debounce_timers[user_id].cancel()
        
        # 创建新的防抖计时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.debounce_delay,
            lambda: asyncio.create_task(self._process_debounced_messages(user_id))
        )
        self.debounce_timers[user_id] = timer
    
    async def _process_debounced_messages(self, user_id: str):
        """处理防抖后的消息"""
        # 从缓冲区取出消息
        if user_id not in self.message_buffer or not self.message_buffer[user_id]:
            return
        
        # 取出消息并清空缓冲区
        messages = self.message_buffer[user_id].copy()
        self.message_buffer[user_id].clear()
        
        # 移除对应的防抖计时器
        if user_id in self.debounce_timers:
            del self.debounce_timers[user_id]
        
        # 合并消息
        combined_message = "\n".join(messages)
        logger.info(f"处理防抖后的消息: {user_id} - {combined_message}")
        
        # 调用消息处理回调
        if self.message_handler:
            try:
                await self.message_handler(user_id, combined_message)
            except Exception as e:
                logger.error(f"处理防抖消息时发生异常: {e}")
    
    async def send_message(self, user_id: str, message: str) -> bool:
        """发送消息到指定用户"""
        if not self.websocket or not self.running:
            logger.error("WebSocket 未连接，无法发送消息")
            return False
        
        try:
            # 构建消息格式（OneBot V11 协议格式）
            # 根据用户ID判断是私聊还是群聊
            if user_id.startswith('group_'):
                # 群消息格式
                group_id = user_id.split('_')[1]  # 提取群ID
                message_data = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": int(group_id),
                        "message": message
                    }
                }
            else:
                # 私聊消息格式
                message_data = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": int(user_id),
                        "message": message
                    }
                }
            
            await self.websocket.send(json.dumps(message_data))
            logger.info(f"发送消息成功: {user_id} - {message}")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def start(self):
        """启动 WebSocket 客户端"""
        self.running = True
        logger.info("启动 NapCat WebSocket 客户端...")
        await self.connect()
    
    async def stop(self):
        """停止 WebSocket 客户端"""
        self.running = False
        logger.info("停止 NapCat WebSocket 客户端...")
        
        # 取消所有防抖计时器
        for timer in self.debounce_timers.values():
            timer.cancel()
        self.debounce_timers.clear()
        
        # 关闭 WebSocket 连接
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None

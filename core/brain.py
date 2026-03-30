import asyncio
import json
import os
from typing import Dict, List, Any
from loguru import logger

from config.settings import settings
from core.llm_client import LLMClient
from memory.faiss_mgr import FAISSManager
from memory.sqlite_db import SQLiteDB


class Brain:
    """大脑中枢调度器：整个系统的指挥官，串联所有流程"""
    
    def __init__(self, send_callback=None):
        """初始化大脑中枢"""
        self.llm_client = LLMClient()
        self.send_callback = send_callback  # 保存发送消息的钩子
        self.sqlite_db = SQLiteDB()
        self.faiss_mgr = FAISSManager()
        
        # 初始化数据库
        # 移除 Brain.__init__ 中的 create_task，改在 main.py 的 lifespan 钩子中处理
        pass
        
        # 用户会话管理
        self.user_sessions: Dict[str, Dict] = {}
        # 短期记忆文件路径
        self.short_term_file_path = "bot/zhangqinxi/short_term.json"
    
    async def _init_db(self):
        """初始化数据库"""
        await self.sqlite_db.init_db()
    
    async def handle_message(self, user_id: str, message: str):
        """
        处理用户消息的主入口
        
        Args:
            user_id: 用户ID
            message: 用户消息内容
        """
        logger.info(f"收到用户 {user_id} 的消息: {message}")
        
        try:
            # 调用LLM获取回复
            response = await self._process_message(user_id, message)
            
            # 发送回复到NapCat
            if self.send_callback:
                await self.send_callback(user_id, response)
            logger.info(f"向用户 {user_id} 发送回复: {response}")
            
        except Exception as e:
            logger.error(f"处理用户 {user_id} 消息时发生异常: {e}")
            # 发送错误信息给用户
            error_response = "抱歉，我在处理您的消息时遇到了一些问题，请稍后再试。"
            
            # 发送错误回复到NapCat
            if self.send_callback:
                await self.send_callback(user_id, error_response)
            logger.info(f"向用户 {user_id} 发送错误回复: {error_response}")
    
    async def _process_message(self, user_id: str, message: str) -> str:
        """
        处理消息的核心逻辑
        
        执行流：
        1. 获取用户会话或创建新会话
        2. 获取Embedding向量
        3. 调用FAISS搜索最匹配的ID
        4. 从SQLite查询对应的长期记忆文本
        5. 读取角色设定和短期记忆
        6. 组装终极Prompt
        7. 调用LLM生成回复
        8. 更新短期记忆
        
        Args:
            user_id: 用户ID
            message: 用户消息内容
            
        Returns:
            str: AI回复内容
        """
        # 1. 获取或初始化用户会话
        if user_id not in self.user_sessions:
            # 从文件加载短期记忆
            short_term_memory = await self._load_short_term_memory(user_id)
            self.user_sessions[user_id] = {
                "short_term_memory": short_term_memory,  # 短期记忆（最近N轮对话）
                "character_info": await self._load_character_info(user_id),  # 角色信息
            }
        
        session = self.user_sessions[user_id]
        
        # 2. 构建对话历史（包含当前消息）
        conversation_history = session["short_term_memory"].copy()
        conversation_history.append({"role": "user", "content": message})
        
        # 3. 从长期记忆中检索相关信息
        long_term_context = await self._retrieve_long_term_memory(message, user_id)
        
        # 4. 构建完整提示词
        full_prompt = await self._build_full_prompt(
            session["character_info"],
            conversation_history,
            ""  # 暂时无长期记忆上下文
        )
        
        # 5. 调用LLM生成回复
        response = await self.llm_client.generate_chat(full_prompt)
        
        # 6. 更新短期记忆（添加用户消息和AI回复）
        conversation_history.append({"role": "assistant", "content": response})
        # 限制短期记忆大小
        updated_memory = conversation_history[-settings.SHORT_TERM_MEMORY_SIZE:]
        session["short_term_memory"] = updated_memory
        
        # 7. 保存短期记忆到文件
        await self._save_short_term_memory(user_id, updated_memory)
        
        # 8. 检查是否需要执行"满百归十"逻辑
        await self._check_and_summarize_memory(user_id)
        
        return response
    
    async def _load_short_term_memory(self, user_id: str) -> List[Dict[str, str]]:
        """
        从文件加载短期记忆
        
        Args:
            user_id: 用户ID
            
        Returns:
            List[Dict[str, str]]: 短期记忆列表
        """
        file_path = self.short_term_file_path
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 过滤掉系统消息，只保留用户和助手的对话
                    return [item for item in data if item.get("role") in ["user", "assistant"]]
            except Exception as e:
                logger.error(f"加载短期记忆文件失败: {e}")
                return []
        return []
    
    async def _save_short_term_memory(self, user_id: str, memory: List[Dict[str, str]]):
        """
        保存短期记忆到文件
        
        Args:
            user_id: 用户ID
            memory: 短期记忆列表
        """
        file_path = self.short_term_file_path
        # 读取现有文件内容，保留系统消息
        existing_data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = []
        
        # 保留系统消息，替换其他内容
        filtered_data = [item for item in existing_data if item.get("role") == "system"]
        filtered_data.extend(memory)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(filtered_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存短期记忆文件失败: {e}")
    
    async def _load_character_info(self, user_id: str) -> Dict[str, Any]:
        """
        从 character.json 真实加载角色信息
        
        Args:
            user_id: 用户ID（用于确定角色实例）
            
        Returns:
            Dict[str, Any]: 角色信息
        """
        char_file_path = "bot/zhangqinxi/character.json"
        if os.path.exists(char_file_path):
            try:
                with open(char_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载角色设定失败: {e}")
        
        # 如果文件不存在的兜底返回
        logger.warning("未找到 character.json，使用兜底设定")
        return {
            "name": "张情兮",
            "personality": "温柔、体贴",
            "background": "AI女友",
            "style": "友好"
        }
    
    async def _retrieve_long_term_memory(self, query: str, user_id: str) -> str:
        """从长期记忆中精准检索相关信息"""
        try:
            # 1. 将用户当前的发言转化为向量
            query_vector = await self.llm_client.get_embedding(query)
            
            # 2. 使用 FAISS 在本地极速搜索最相似的 top_k 个结果
            # 取回的结果带有 similarity(相似度) 和 metadata
            results = await self.faiss_mgr.search(query_vector, k=settings.TOP_K)
            
            if not results:
                return ""
                
            # 3. 过滤出属于当前 user_id 的记忆，并提取它们在 SQLite 里的 ID
            valid_record_ids = [
                res["metadata"]["record_id"] 
                for res in results 
                if res.get("metadata", {}).get("user_id") == user_id and res["metadata"].get("table") == "user_facts"
            ]
            
            if not valid_record_ids:
                return ""
                
            # 4. 去 SQLite 中把真正的文本取出来
            records = await self.sqlite_db.query_by_ids("user_facts", valid_record_ids)
            
            # 5. 将查询到的长期记忆拼接成一个字符串返回给 Prompt
            memory_texts = [f"- {record['content']}" for record in records]
            return "\n".join(memory_texts)
            
        except Exception as e:
            logger.error(f"提取长期记忆失败: {e}")
            return ""
    
    async def _build_full_prompt(self, character_info: Dict[str, Any], 
                                conversation_history: List[Dict[str, str]], 
                                long_term_context: str) -> List[Dict[str, str]]:
        """
        构建完整提示词
        
        Args:
            character_info: 角色信息
            conversation_history: 对话历史
            long_term_context: 长期记忆上下文
            
        Returns:
            List[Dict[str, str]]: 格式化的对话历史
        """
        # 将数组转换为逗号分隔的字符串，让语言更自然
        personality_str = "、".join(character_info.get('personality', [])) if isinstance(character_info.get('personality'), list) else character_info.get('personality', '')
        hobbies_str = "、".join(character_info.get('hobbies', [])) if isinstance(character_info.get('hobbies'), list) else ''
        
        system_prompt = f"""
你是一个AI女友，名叫{character_info.get('name', '张情兮')}。
你的人格特点是：{personality_str}。
你的背景是：{character_info.get('background', '')}。
你的爱好是：{hobbies_str}。
你的对话风格是：{character_info.get('style', '')}。

请始终保持人设，不要暴露你是AI的身份，使用自然、口语化的中文与我交流。
"""
        
        # 如果有长期记忆上下文，添加到系统提示词中
        if long_term_context:
            system_prompt += f"\n\n以下是相关的长期记忆信息：\n{long_term_context}\n"
        
        # 构建完整提示词
        full_prompt = [{"role": "system", "content": system_prompt}]
        full_prompt.extend(conversation_history)
        
        return full_prompt
    
    async def _check_and_summarize_memory(self, user_id: str):
        """
        检查是否需要执行"满百归十"逻辑
        
        Args:
            user_id: 用户ID
        """
        if user_id not in self.user_sessions:
            return
        
        session = self.user_sessions[user_id]
        memory_length = len(session["short_term_memory"])
        
        # 检查是否达到总结阈值
        if memory_length >= settings.SHORT_TERM_MEMORY_SIZE:
            logger.info(f"用户 {user_id} 的短期记忆达到阈值，开始执行总结逻辑...")
            
            # 启动后台任务进行总结
            asyncio.create_task(self._summarize_memory_background(user_id))
    
    async def _summarize_memory_background(self, user_id: str):
        """
        后台执行记忆总结任务
        
        Args:
            user_id: 用户ID
        """
        try:
            if user_id not in self.user_sessions:
                return
            
            session = self.user_sessions[user_id]
            memory = session["short_term_memory"]
            
            # 截取前90条对话进行总结
            messages_to_summarize = memory[:settings.SUMMARIZE_THRESHOLD]
            
            # 构建总结提示词
            summary_prompt = [
                {
                    "role": "system", 
                    "content": "你是一个对话总结助手。请将以下对话历史总结为关键事实和要点，保留重要的用户信息、偏好和事件。"
                },
                {
                    "role": "user",
                    "content": f"请总结以下对话历史：\n\n{str(messages_to_summarize)}"
                }
            ]
            
            # 调用LLM生成总结
            summary = await self.llm_client.generate_chat(summary_prompt)
            
            # 将总结保存到长期记忆（SQLite和FAISS）
            await self._save_to_long_term_memory(user_id, summary)
            
            # 保留最新的10条对话
            session["short_term_memory"] = memory[settings.SUMMARIZE_THRESHOLD:]
            
            logger.info(f"用户 {user_id} 的记忆总结完成")
        except Exception as e:
            logger.error(f"总结用户 {user_id} 的记忆时发生异常: {e}")
    
    async def _save_to_long_term_memory(self, user_id: str, content: str):
        """保存内容到长期记忆 (双轨制：SQLite 存文本，FAISS 存向量)"""
        try:
            # 1. 将整段总结存入 SQLite 的 user_facts 表
            # 这里的 SQLiteDB 会自动忽略完全重复的插入
            await self.sqlite_db.insert_user_fact(user_id, content)
            
            # 2. 重新从数据库把刚刚存的记录查出来，为了获取它的自增 ID
            facts = await self.sqlite_db.get_user_facts(user_id)
            if not facts: return
            latest_fact_id = facts[0]["id"] # 获取最新那条的 ID
            
            # 3. 调用 LLM 网关，把文本转化为高维向量
            vector = await self.llm_client.get_embedding(content)
            
            # 4. 将向量存入 FAISS，并在 metadata 里绑定 SQLite 的表名和 ID
            metadata = {
                "user_id": user_id,
                "table": "user_facts",
                "record_id": latest_fact_id
            }
            await self.faiss_mgr.add_vector(vector, metadata)
            
            # 5. 保存 FAISS 索引到硬盘
            await self.faiss_mgr.save_index()
            logger.info(f"长期记忆已成功双轨入库 (用户: {user_id}, DB_ID: {latest_fact_id})")
            
        except Exception as e:
            logger.error(f"保存长期记忆失败: {e}")

import aiosqlite
import json
from typing import List, Dict, Any, Optional
from loguru import logger

from config.settings import settings


class SQLiteDB:
    """SQLite 数据库操作类：使用 aiosqlite 封装数据库操作"""
    
    def __init__(self, db_path: str = "bot/zhangqinxi/long_term.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
    
    async def init_db(self):
        """初始化数据库表结构"""
        async with aiosqlite.connect(self.db_path) as db:
            # 创建用户事实表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建关键事件表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS key_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_content TEXT NOT NULL,
                    event_metadata TEXT,  -- JSON格式的元数据
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建机器人状态表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建向量索引关联表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS vector_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    embedding_vector_path TEXT,  -- 存储向量文件路径或标识符
                    related_table TEXT NOT NULL,  -- 关联的表名
                    related_id INTEGER NOT NULL,  -- 关联的记录ID
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建好感度表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS affection (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    affection_score REAL DEFAULT 0.0,
                    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
            logger.info(f"数据库初始化完成: {self.db_path}")
    
    async def insert_user_fact(self, user_id: str, fact: str):
        """
        插入用户事实
        
        Args:
            user_id: 用户ID
            fact: 用户事实内容
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO user_facts (user_id, fact) 
                VALUES (?, ?)
            ''', (user_id, fact))
            await db.commit()
            logger.debug(f"插入用户事实: {user_id} - {fact}")
    
    async def insert_key_event(self, user_id: str, event_type: str, event_content: str, 
                              event_metadata: Optional[Dict] = None):
        """
        插入关键事件
        
        Args:
            user_id: 用户ID
            event_type: 事件类型
            event_content: 事件内容
            event_metadata: 事件元数据
        """
        metadata_str = json.dumps(event_metadata) if event_metadata else None
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO key_events (user_id, event_type, event_content, event_metadata) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, event_type, event_content, metadata_str))
            await db.commit()
            logger.debug(f"插入关键事件: {user_id} - {event_type} - {event_content}")
    
    async def insert_affection(self, user_id: str, affection_score: float):
        """
        插入或更新好感度
        
        Args:
            user_id: 用户ID
            affection_score: 好感度分数
        """
        async with aiosqlite.connect(self.db_path) as db:
            # 检查是否已存在该用户的好感度记录
            cursor = await db.execute(
                'SELECT id FROM affection WHERE user_id = ?', 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                # 更新现有记录
                await db.execute('''
                    UPDATE affection 
                    SET affection_score = ?, last_interaction = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (affection_score, user_id))
            else:
                # 插入新记录
                await db.execute('''
                    INSERT INTO affection (user_id, affection_score) 
                    VALUES (?, ?)
                ''', (user_id, affection_score))
            
            await db.commit()
            logger.debug(f"更新好感度: {user_id} - {affection_score}")
    
    async def get_user_facts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户事实
        
        Args:
            user_id: 用户ID
            
        Returns:
            List[Dict[str, Any]]: 用户事实列表
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT id, fact, created_at FROM user_facts WHERE user_id = ? ORDER BY created_at DESC',
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            facts = []
            for row in rows:
                facts.append({
                    "id": row[0],
                    "fact": row[1],
                    "created_at": row[2]
                })
            
            return facts
    
    async def get_key_events(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取关键事件
        
        Args:
            user_id: 用户ID
            limit: 限制返回数量
            
        Returns:
            List[Dict[str, Any]]: 关键事件列表
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, event_type, event_content, event_metadata, created_at 
                FROM key_events 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            rows = await cursor.fetchall()
            
            events = []
            for row in rows:
                event = {
                    "id": row[0],
                    "event_type": row[1],
                    "event_content": row[2],
                    "created_at": row[4]
                }
                
                # 解析元数据
                if row[3]:
                    try:
                        event["event_metadata"] = json.loads(row[3])
                    except json.JSONDecodeError:
                        event["event_metadata"] = {}
                
                events.append(event)
            
            return events
    
    async def get_affection(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户好感度
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict[str, Any]]: 好感度信息
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT affection_score, last_interaction FROM affection WHERE user_id = ?', 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                return {
                    "affection_score": row[0],
                    "last_interaction": row[1]
                }
            
            return None
    
    async def query_by_ids(self, table_name: str, ids: List[int]) -> List[Dict[str, Any]]:
        """
        根据ID列表批量查询文本
        
        Args:
            table_name: 表名
            ids: ID列表
            
        Returns:
            List[Dict[str, Any]]: 查询结果列表
        """
        if not ids:
            return []
        
        # 构建占位符
        placeholders = ','.join(['?' for _ in ids])
        
        async with aiosqlite.connect(self.db_path) as db:
            # 根据表名选择不同的查询语句
            if table_name == "user_facts":
                query = f'''
                    SELECT id, user_id, fact, created_at 
                    FROM user_facts 
                    WHERE id IN ({placeholders})
                '''
                cursor = await db.execute(query, ids)
                rows = await cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "user_id": row[1],
                        "content": row[2],
                        "created_at": row[3],
                        "type": "fact"
                    })
                
                return results
            
            elif table_name == "key_events":
                query = f'''
                    SELECT id, user_id, event_content, created_at 
                    FROM key_events 
                    WHERE id IN ({placeholders})
                '''
                cursor = await db.execute(query, ids)
                rows = await cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "user_id": row[1],
                        "content": row[2],
                        "created_at": row[3],
                        "type": "event"
                    })
                
                return results
            
            else:
                logger.error(f"不支持的表名: {table_name}")
                return []
    
    async def close(self):
        """关闭数据库连接"""
        # aiosqlite 使用上下文管理器，无需显式关闭
        pass
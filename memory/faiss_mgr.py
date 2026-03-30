import faiss
import numpy as np
import pickle
import os
from typing import List, Dict, Any, Optional
from loguru import logger

from config.settings import settings


class FAISSManager:
    """FAISS 向量检索管理器：使用 FAISS 库进行向量检索"""
    
    def __init__(self, index_path: str = "bot/zhangqinxi/vector_index.faiss", 
                 metadata_path: str = "bot/zhangqinxi/vector_metadata.pkl"):
        """
        初始化 FAISS 管理器
        
        Args:
            index_path: 索引文件路径
            metadata_path: 元数据文件路径
        """
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index: Optional[faiss.Index] = None
        self.metadata: Dict[int, Dict[str, Any]] = {}
        
        # 创建目录（如果不存在）
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
    
    async def load_index(self):
        """加载本地索引文件"""
        try:
            if os.path.exists(self.index_path):
                # 加载索引
                self.index = faiss.read_index(self.index_path)
                logger.info(f"成功加载索引文件: {self.index_path}")
            else:
                # 如果索引文件不存在，创建一个新的
                self.index = faiss.IndexFlatIP(1536)  # 假设使用1536维的嵌入向量
                logger.info("创建新索引")
            
            # 加载元数据
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, 'rb') as f:
                    self.metadata = pickle.load(f)
                logger.info(f"成功加载元数据文件: {self.metadata_path}")
            else:
                logger.info("元数据文件不存在，创建空元数据")
                
        except Exception as e:
            logger.error(f"加载索引文件时发生错误: {e}")
            # 创建新的索引
            self.index = faiss.IndexFlatIP(1536)
            self.metadata = {}
    
    async def save_index(self):
        """保存索引到本地文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            
            # 保存索引
            faiss.write_index(self.index, self.index_path)
            
            # 保存元数据
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
            
            logger.info(f"成功保存索引文件: {self.index_path}")
            
        except Exception as e:
            logger.error(f"保存索引文件时发生错误: {e}")
    
    async def add_vector(self, vector: List[float], metadata: Dict[str, Any]) -> int:
        """
        添加向量到索引
        
        Args:
            vector: 要添加的向量
            metadata: 向量的元数据
            
        Returns:
            int: 添加的向量的ID
        """
        # 确保索引已加载
        if self.index is None:
            await self.load_index()
        
        # 将向量转换为numpy数组
        vector_array = np.array([vector], dtype=np.float32)
        
        # 对于内积索引，需要标准化向量
        faiss.normalize_L2(vector_array)
        
        # 获取当前索引中的向量数量作为新向量的ID
        new_id = self.index.ntotal
        
        # 添加向量到索引
        self.index.add(vector_array)
        
        # 保存元数据
        self.metadata[new_id] = metadata
        
        logger.debug(f"添加向量 ID {new_id} 到索引")
        
        return new_id
    
    async def add_vectors(self, vectors: List[List[float]], metadatas: List[Dict[str, Any]]) -> List[int]:
        """
        批量添加向量到索引
        
        Args:
            vectors: 要添加的向量列表
            metadatas: 向量的元数据列表
            
        Returns:
            List[int]: 添加的向量的ID列表
        """
        # 确保索引已加载
        if self.index is None:
            await self.load_index()
        
        if len(vectors) != len(metadatas):
            raise ValueError("向量列表和元数据列表长度不匹配")
        
        # 将向量转换为numpy数组
        vector_array = np.array(vectors, dtype=np.float32)
        
        # 对于内积索引，需要标准化向量
        faiss.normalize_L2(vector_array)
        
        # 获取当前索引中的向量数量作为新向量的起始ID
        start_id = self.index.ntotal
        ids = list(range(start_id, start_id + len(vectors)))
        
        # 添加向量到索引
        self.index.add(vector_array)
        
        # 保存元数据
        for i, metadata in enumerate(metadatas):
            self.metadata[ids[i]] = metadata
        
        logger.debug(f"批量添加向量 IDs {ids} 到索引")
        
        return ids
    
    async def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索最相似的向量
        
        Args:
            query_vector: 查询向量
            k: 返回最相似的k个结果
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        # 确保索引已加载
        if self.index is None:
            await self.load_index()
        
        # 限制k值不超过索引中的向量数量
        k = min(k, self.index.ntotal)
        
        if k <= 0:
            return []
        
        # 将查询向量转换为numpy数组
        query_array = np.array([query_vector], dtype=np.float32)
        
        # 标准化查询向量
        faiss.normalize_L2(query_array)
        
        # 执行搜索
        similarities, indices = self.index.search(query_array, k)
        
        # 构建结果
        results = []
        for i in range(k):
            idx = indices[0][i]
            if idx != -1 and idx in self.metadata:  # 检查索引是否有效且在元数据中存在
                result = {
                    "id": int(idx),
                    "similarity": float(similarities[0][i]),
                    "metadata": self.metadata[idx]
                }
                results.append(result)
        
        logger.debug(f"搜索完成，返回 {len(results)} 个结果")
        
        return results
    
    async def get_vector(self, id: int) -> Optional[List[float]]:
        """
        获取指定ID的向量（如果FAISS支持）
        
        注意：FAISS 不直接支持获取特定ID的向量，此方法可能不可用
        """
        # FAISS 不直接支持获取特定ID的向量，这是一个限制
        logger.warning("FAISS不支持直接获取特定ID的向量")
        return None
    
    async def remove_vector(self, id: int):
        """
        删除指定ID的向量
        
        注意：FAISS 不支持直接删除向量，此方法是一个占位符
        """
        # FAISS 不直接支持删除向量，这是一个限制
        logger.warning("FAISS不支持直接删除向量")
        # 这里可以考虑标记删除，但实际的处理会比较复杂
    
    async def get_index_stats(self) -> Dict[str, Any]:
        """
        获取索引统计信息
        
        Returns:
            Dict[str, Any]: 索引统计信息
        """
        if self.index is None:
            await self.load_index()
        
        stats = {
            "total_vectors": self.index.ntotal,
            "dimension": self.index.d,
            "metadata_count": len(self.metadata)
        }
        
        return stats
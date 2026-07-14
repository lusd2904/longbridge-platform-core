"""
消息队列模块
基于Redis实现任务队列
"""

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from utils.redis_client import redis_client

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""

    AI_ANALYSIS = "ai_analysis"  # AI分析任务
    TRADE_EXECUTION = "trade_execution"  # 交易执行任务
    DATA_SYNC = "data_sync"  # 数据同步任务
    REPORT_GENERATION = "report_generation"  # 报告生成任务
    NOTIFICATION = "notification"  # 通知任务


class TaskPriority(Enum):
    """任务优先级"""

    HIGH = 1
    NORMAL = 2
    LOW = 3


class Task:
    """任务对象"""

    def __init__(
        self,
        task_type: TaskType,
        data: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        task_id: str | None = None,
    ):
        self.task_id = task_id or str(uuid.uuid4())
        self.task_type = task_type
        self.data = data
        self.priority = priority
        self.status = "pending"  # pending, processing, completed, failed
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.result = None
        self.error = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "data": self.data,
            "priority": self.priority.value,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """从字典创建"""
        task = cls(
            task_type=TaskType(data["task_type"]),
            data=data["data"],
            priority=TaskPriority(data["priority"]),
            task_id=data["task_id"],
        )
        task.status = data["status"]
        task.created_at = data["created_at"]
        task.updated_at = data["updated_at"]
        task.result = data.get("result")
        task.error = data.get("error")
        return task


class MessageQueue:
    """消息队列"""

    def __init__(self):
        self.task_handlers: dict[TaskType, Callable[[Task], Any]] = {}
        self.running = False
        self.worker_thread = None
        self.queue_key = "task_queue"
        self.processing_key = "task_processing"
        self.result_key_prefix = "task_result:"

    def register_handler(self, task_type: TaskType, handler: Callable[[Task], Any]):
        """注册任务处理器"""
        self.task_handlers[task_type] = handler
        logger.info(f"注册任务处理器: {task_type.value}")

    def submit_task(self, task: Task, delay: int = 0) -> str:
        """
        提交任务到队列
        :param task: 任务对象
        :param delay: 延迟执行秒数
        :return: 任务ID
        """
        try:
            task_data = json.dumps(task.to_dict(), ensure_ascii=False)

            if delay > 0:
                # 延迟任务，使用zset
                execute_time = time.time() + delay
                redis_client.client.zadd(f"{self.queue_key}:delayed", {task_data: execute_time})
            else:
                # 立即执行，使用list，高优先级在前
                if task.priority == TaskPriority.HIGH:
                    redis_client.client.lpush(self.queue_key, task_data)
                else:
                    redis_client.client.rpush(self.queue_key, task_data)

            logger.info(f"任务提交成功: {task.task_id}, 类型: {task.task_type.value}")
            return task.task_id

        except Exception as e:
            logger.error(f"任务提交失败: {e}")
            raise

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态"""
        try:
            # 先检查结果
            result = redis_client.get_json(f"{self.result_key_prefix}{task_id}")
            if result:
                return result

            # 检查处理中的任务
            processing = redis_client.hget(self.processing_key, task_id)
            if processing:
                return json.loads(processing)

            return None

        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None

    def _move_delayed_tasks(self):
        """将到期的延迟任务移动到主队列"""
        try:
            now = time.time()
            delayed_key = f"{self.queue_key}:delayed"

            # 获取到期的任务
            tasks = redis_client.client.zrangebyscore(delayed_key, 0, now)

            for task_data in tasks:
                # 移动到主队列
                redis_client.client.rpush(self.queue_key, task_data)
                # 从延迟队列删除
                redis_client.client.zrem(delayed_key, task_data)

        except Exception as e:
            logger.error(f"移动延迟任务失败: {e}")

    def _process_task(self, task_data: str):
        """处理单个任务"""
        try:
            task_dict = json.loads(task_data)
            task = Task.from_dict(task_dict)

            # 更新状态为处理中
            task.status = "processing"
            task.updated_at = datetime.now().isoformat()
            redis_client.hset(self.processing_key, task.task_id, json.dumps(task.to_dict(), ensure_ascii=False))

            # 获取处理器
            handler = self.task_handlers.get(task.task_type)
            if not handler:
                raise ValueError(f"未找到任务处理器: {task.task_type.value}")

            # 执行任务
            logger.info(f"开始处理任务: {task.task_id}")
            result = handler(task)

            # 更新状态为完成
            task.status = "completed"
            task.result = result
            task.updated_at = datetime.now().isoformat()

            # 保存结果（保留24小时）
            redis_client.set(f"{self.result_key_prefix}{task.task_id}", task.to_dict(), expire=86400)

            # 从处理中删除
            redis_client.client.hdel(self.processing_key, task.task_id)

            logger.info(f"任务处理完成: {task.task_id}")

        except Exception as e:
            logger.error(f"任务处理失败: {e}")

            # 更新状态为失败
            task.status = "failed"
            task.error = str(e)
            task.updated_at = datetime.now().isoformat()

            # 保存失败结果
            redis_client.set(f"{self.result_key_prefix}{task.task_id}", task.to_dict(), expire=86400)

            # 从处理中删除
            redis_client.client.hdel(self.processing_key, task.task_id)

    def _worker_loop(self):
        """工作线程循环"""
        logger.info("消息队列工作线程启动")

        while self.running:
            try:
                # 移动延迟任务
                self._move_delayed_tasks()

                # 获取任务（阻塞等待，超时1秒）
                result = redis_client.client.blpop(self.queue_key, timeout=1)

                if result:
                    _, task_data = result
                    self._process_task(task_data)

            except Exception as e:
                logger.error(f"工作线程错误: {e}")
                time.sleep(1)

        logger.info("消息队列工作线程停止")

    def start(self):
        """启动消息队列"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            logger.info("消息队列已启动")

    def stop(self):
        """停止消息队列"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("消息队列已停止")

    def get_queue_length(self) -> int:
        """获取队列长度"""
        try:
            return redis_client.llen(self.queue_key)
        except Exception as e:
            logger.error(f"获取队列长度失败: {e}")
            return 0


# 全局消息队列实例
message_queue = MessageQueue()


# 便捷函数
def submit_ai_analysis_task(symbol: str, data: dict[str, Any], priority: TaskPriority = TaskPriority.NORMAL) -> str:
    """提交AI分析任务"""
    task = Task(task_type=TaskType.AI_ANALYSIS, data={"symbol": symbol, **data}, priority=priority)
    return message_queue.submit_task(task)


def submit_trade_task(symbol: str, action: str, quantity: float, priority: TaskPriority = TaskPriority.HIGH) -> str:
    """提交交易任务"""
    task = Task(
        task_type=TaskType.TRADE_EXECUTION,
        data={"symbol": symbol, "action": action, "quantity": quantity},
        priority=priority,
    )
    return message_queue.submit_task(task)

"""
统一配置管理模块
支持从环境变量和.env文件加载配置
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 优先加载当前项目根目录的 .env，避免误读其它历史目录配置
PROJECT_ROOT = Path(__file__).resolve().parents[3]
possible_paths = [
    PROJECT_ROOT / '.env',
    PROJECT_ROOT / 'backend-server' / '.env',
]

env_loaded = False
for env_path in possible_paths:
    if env_path.exists():
        load_dotenv(env_path, override=False)
        env_loaded = True
        break

if not env_loaded:
    # 尝试从当前工作目录向上查找
    cwd = Path.cwd()
    for _ in range(3):
        env_path = cwd / '.env'
        if env_path.exists():
            load_dotenv(env_path, override=False)
            break
        cwd = cwd.parent


class Settings:
    """应用配置类"""
    
    # 数据库配置
    DB_HOST: str = os.getenv('DB_HOST', 'localhost')
    DB_PORT: int = int(os.getenv('DB_PORT', 3306))
    DB_USER: str = os.getenv('DB_USER', 'root')
    DB_PASSWORD: str = os.getenv('DB_PASSWORD', '')
    DB_NAME: str = os.getenv('DB_NAME', 'quant_trade')
    DB_CHARSET: str = os.getenv('DB_CHARSET', 'utf8mb4')
    DB_READ_ENABLED: bool = os.getenv('DB_READ_ENABLED', 'false').lower() == 'true'
    DB_READ_HOST: str = os.getenv('DB_READ_HOST', DB_HOST)
    DB_READ_PORT: int = int(os.getenv('DB_READ_PORT', str(DB_PORT)))
    DB_READ_USER: str = os.getenv('DB_READ_USER', DB_USER)
    DB_READ_PASSWORD: str = os.getenv('DB_READ_PASSWORD', DB_PASSWORD)
    DB_READ_NAME: str = os.getenv('DB_READ_NAME', DB_NAME)
    DB_READ_CHARSET: str = os.getenv('DB_READ_CHARSET', DB_CHARSET)
    
    # Redis配置
    REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT: int = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD: Optional[str] = os.getenv('REDIS_PASSWORD')
    REDIS_DB: int = int(os.getenv('REDIS_DB', 0))
    REDIS_CLUSTER_ENABLED: bool = os.getenv('REDIS_CLUSTER_ENABLED', 'false').lower() == 'true'
    REDIS_CLUSTER_NODES: str = os.getenv('REDIS_CLUSTER_NODES', '')
    
    # JWT配置
    JWT_SECRET_KEY: str = os.getenv('JWT_SECRET_KEY', 'default-secret-key')
    JWT_EXPIRE_HOURS: int = int(os.getenv('JWT_EXPIRE_HOURS', 24))
    
    # Ollama配置
    OLLAMA_BASE_URL: str = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    OLLAMA_MODEL: str = os.getenv('OLLAMA_MODEL', 'gemma3:12b')
    OLLAMA_TIMEOUT: int = int(os.getenv('OLLAMA_TIMEOUT', 120))
    OLLAMA_NUM_THREAD: int = int(os.getenv('OLLAMA_NUM_THREAD', 8))
    OLLAMA_TEMPERATURE: float = float(os.getenv('OLLAMA_TEMPERATURE', 0.7))
    
    # 应用配置
    APP_ENV: str = os.getenv('APP_ENV', 'development')
    APP_DEBUG: bool = os.getenv('APP_DEBUG', 'true').lower() == 'true'
    APP_PORT: int = int(os.getenv('APP_PORT', 5001))
    APP_HOST: str = os.getenv('APP_HOST', '0.0.0.0')
    CORS_ALLOWED_ORIGINS: str = os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173'
    )
    
    # 日志配置
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'logs/app.log')
    LOG_MAX_BYTES: int = int(os.getenv('LOG_MAX_BYTES', 10485760))
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', 5))
    
    # InfluxDB时序数据库配置
    INFLUXDB_URL: str = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
    INFLUXDB_TOKEN: str = os.getenv('INFLUXDB_TOKEN', '')
    INFLUXDB_ORG: str = os.getenv('INFLUXDB_ORG', 'quant-trade')
    INFLUXDB_BUCKET: str = os.getenv('INFLUXDB_BUCKET', 'market_data')

    # Kafka 流处理配置
    KAFKA_ENABLED: bool = os.getenv('KAFKA_ENABLED', 'false').lower() == 'true'
    KAFKA_BROKERS: str = os.getenv('KAFKA_BROKERS', 'localhost:9092')
    KAFKA_MARKET_TOPIC: str = os.getenv('KAFKA_MARKET_TOPIC', 'market.quotes')
    KAFKA_TRADE_COMMAND_TOPIC: str = os.getenv('KAFKA_TRADE_COMMAND_TOPIC', 'trade.commands')
    KAFKA_TRADE_EVENT_TOPIC: str = os.getenv('KAFKA_TRADE_EVENT_TOPIC', 'trade.events')
    KAFKA_CONSUMER_GROUP: str = os.getenv('KAFKA_CONSUMER_GROUP', 'longbridge-trade-local')

    # TimescaleDB 配置
    TIMESCALE_ENABLED: bool = os.getenv('TIMESCALE_ENABLED', 'false').lower() == 'true'
    TIMESCALE_DSN: str = os.getenv('TIMESCALE_DSN', '')

    # DataOps 配置
    DATAOPS_ENABLED: bool = os.getenv('DATAOPS_ENABLED', 'true').lower() == 'true'
    DATAOPS_STRICT_MODE: bool = os.getenv('DATAOPS_STRICT_MODE', 'false').lower() == 'true'

    # WebSocket 行情推送
    WEBSOCKET_ENABLED: bool = os.getenv('WEBSOCKET_ENABLED', 'true').lower() == 'true'
    WEBSOCKET_QUOTE_INTERVAL: int = int(os.getenv('WEBSOCKET_QUOTE_INTERVAL', 2))

    # FastAPI trade-service
    TRADE_SERVICE_ENABLED: bool = os.getenv('TRADE_SERVICE_ENABLED', 'false').lower() == 'true'
    TRADE_SERVICE_URL: str = os.getenv('TRADE_SERVICE_URL', 'http://127.0.0.1:8002')
    TRADE_SERVICE_TIMEOUT: int = int(os.getenv('TRADE_SERVICE_TIMEOUT', 30))
    
    @classmethod
    def get_db_url(cls) -> str:
        """获取数据库连接URL"""
        return f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}?charset={cls.DB_CHARSET}"
    
    @classmethod
    def get_db_config(cls) -> dict:
        """获取数据库配置字典"""
        return {
            'host': cls.DB_HOST,
            'port': cls.DB_PORT,
            'user': cls.DB_USER,
            'password': cls.DB_PASSWORD,
            'database': cls.DB_NAME,
            'charset': cls.DB_CHARSET
        }

    @classmethod
    def get_db_read_config(cls) -> dict:
        """获取读库配置字典，未启用时回退主库。"""
        if not cls.DB_READ_ENABLED:
            return cls.get_db_config()

        return {
            'host': cls.DB_READ_HOST,
            'port': cls.DB_READ_PORT,
            'user': cls.DB_READ_USER,
            'password': cls.DB_READ_PASSWORD,
            'database': cls.DB_READ_NAME,
            'charset': cls.DB_READ_CHARSET
        }

    @classmethod
    def is_read_db_enabled(cls) -> bool:
        return cls.DB_READ_ENABLED
    
    @classmethod
    def get_redis_config(cls) -> dict:
        """获取Redis配置字典"""
        return {
            'host': cls.REDIS_HOST,
            'port': cls.REDIS_PORT,
            'password': cls.REDIS_PASSWORD,
            'db': cls.REDIS_DB,
            'cluster_enabled': cls.REDIS_CLUSTER_ENABLED,
            'cluster_nodes': cls.REDIS_CLUSTER_NODES,
            'decode_responses': True
        }

    @classmethod
    def get_kafka_config(cls) -> dict:
        """获取 Kafka 配置字典"""
        brokers = [item.strip() for item in cls.KAFKA_BROKERS.split(',') if item.strip()]
        return {
            'enabled': cls.KAFKA_ENABLED,
            'brokers': brokers,
            'market_topic': cls.KAFKA_MARKET_TOPIC,
            'trade_command_topic': cls.KAFKA_TRADE_COMMAND_TOPIC,
            'trade_event_topic': cls.KAFKA_TRADE_EVENT_TOPIC,
            'consumer_group': cls.KAFKA_CONSUMER_GROUP
        }

    @classmethod
    def get_cors_origins(cls):
        """获取当前环境允许的 CORS 来源。"""
        raw = str(cls.CORS_ALLOWED_ORIGINS or '').strip()
        if not raw or raw == '*':
            return '*'
        return [item.strip() for item in raw.split(',') if item.strip()]
    
    @classmethod
    def is_development(cls) -> bool:
        """是否为开发环境"""
        return cls.APP_ENV == 'development'
    
    @classmethod
    def is_production(cls) -> bool:
        """是否为生产环境"""
        return cls.APP_ENV == 'production'


# 全局配置实例
settings = Settings()

import threading
import time

import requests

from config.Config import AppConfig
from utils.MonitorLink import MonitorLink


class AIAnalyst:
    _nvidia_rate_lock = threading.Lock()
    _nvidia_call_times: list[float] = []
    _provider_cooldown_lock = threading.Lock()
    _provider_failures: dict[str, dict[str, object]] = {}
    _provider_inflight: dict[str, float] = {}
    _ollama_models_cache: dict[str, object] = {"at": 0.0, "models": []}
    OFFICIAL_CLOUD_MODEL_IDS: list[str] = [
        "gpt-5.5",
        "gpt-5.4",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-nano-12b-v2-vl",
        "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        "deepseek-ai/deepseek-r1-distill-llama-8b",
        "qwen/qwen3.5-397b-a17b",
        "meta/llama-3.2-90b-vision-instruct",
        "minimaxai/minimax-m2.5",
        "minimaxai/minimax-m2.1",
        "z-ai/glm4.7",
    ]
    MODEL_ID_ALIASES: dict[str, str] = {
        "coordinator-agent/openai/gpt-oss-120b": "openai/gpt-oss-120b",
        "coordinator-agent/openai/gpt-oss-20b": "openai/gpt-oss-20b",
        "coordinator-agent/nvidia/nemotron-3-super-120b-a12b": "nvidia/nemotron-3-super-120b-a12b",
        "coordinator-agent/nvidia/nemotron-3-super": "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-super": "nvidia/nemotron-3-super-120b-a12b",
        "coordinator-agent/nvidia/nemotron-nano-12b-v2-vl": "nvidia/nemotron-nano-12b-v2-vl",
        "nvidia/nemotron-nano-12b-vl": "nvidia/nemotron-nano-12b-v2-vl",
        "coordinator-agent/nvidia/llama-3.1-nemotron-nano-vl-8b-v1": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "coordinator-agent/nvidia/llama-3.1-nemotron-ultra-253b-v1": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        "coordinator-agent/deepseek-ai/deepseek-r1-distill-llama-8b": "deepseek-ai/deepseek-r1-distill-llama-8b",
        "coordinator-agent/qwen/qwen3.5-397b-a17b": "qwen/qwen3.5-397b-a17b",
        "coordinator-agent/meta/llama-3.2-90b-vision-instruct": "meta/llama-3.2-90b-vision-instruct",
        "coordinator-agent/minimaxai/minimax-m2.5": "minimaxai/minimax-m2.5",
        "coordinator-agent/minimaxai/minimax-m2.1": "minimaxai/minimax-m2.1",
        "coordinator-agent/z-ai/glm4.7": "z-ai/glm4.7",
    }
    CONFIG_MODEL_FIELDS: list[str] = [
        "ai_model",
        "ai_model_scan_pulse",
        "ai_model_scan_fast",
        "ai_model_scan_risk",
        "ai_model_scan_final",
        "ai_model_trend_batch",
        "ai_model_recommend_brief",
        "ai_model_recommend_summary",
        "ai_model_vision",
    ]
    MODEL_CATALOG: dict[str, dict[str, object]] = {
        "gpt-5.5": {
            "alias": "gpt-5.5",
            "provider": "sub2api",
            "latency": "medium",
            "best_for": ["复杂投研", "交易终审", "高质量总结"],
        },
        "gpt-5.4": {
            "alias": "gpt-5.4",
            "provider": "sub2api",
            "latency": "fast",
            "best_for": ["快速扫描", "风险筛查", "批量摘要"],
        },
        "coordinator-agent/openai/gpt-oss-120b": {
            "alias": "gpt-oss-120b",
            "provider": "openai",
            "latency": "medium",
            "best_for": ["复杂推理", "长文总结", "高质量终审"],
        },
        "openai/gpt-oss-120b": {
            "alias": "gpt-oss-120b",
            "provider": "openai",
            "latency": "medium",
            "best_for": ["复杂推理", "长文总结", "高质量终审"],
        },
        "coordinator-agent/openai/gpt-oss-20b": {
            "alias": "gpt-oss-20b",
            "provider": "openai",
            "latency": "fast",
            "best_for": ["快速扫描", "短摘要", "低时延问答"],
        },
        "openai/gpt-oss-20b": {
            "alias": "gpt-oss-20b",
            "provider": "openai",
            "latency": "fast",
            "best_for": ["快速扫描", "短摘要", "低时延问答"],
        },
        "coordinator-agent/nvidia/nemotron-3-super-120b-a12b": {
            "alias": "nemotron-3-super",
            "provider": "nvidia",
            "latency": "medium",
            "best_for": ["综合分析", "交易终审", "大盘联动判断"],
        },
        "coordinator-agent/nvidia/nemotron-nano-12b-v2-vl": {
            "alias": "nemotron-nano-12b-vl",
            "provider": "nvidia",
            "latency": "fast",
            "best_for": ["轻量视觉理解", "截图识别", "快速图像问答"],
        },
        "nvidia/nemotron-nano-12b-v2-vl": {
            "alias": "nemotron-nano-12b-vl",
            "provider": "nvidia",
            "latency": "fast",
            "best_for": ["官方 NIM 视觉", "快速图像问答"],
        },
        "coordinator-agent/nvidia/llama-3.1-nemotron-nano-vl-8b-v1": {
            "alias": "nemotron-nano-8b-vl",
            "provider": "nvidia",
            "latency": "fast",
            "best_for": ["低成本视觉", "轻量多模态"],
        },
        "nvidia/llama-3.1-nemotron-nano-vl-8b-v1": {
            "alias": "nemotron-nano-8b-vl",
            "provider": "nvidia",
            "latency": "fast",
            "best_for": ["官方 NIM 视觉", "轻量多模态"],
        },
        "coordinator-agent/nvidia/llama-3.1-nemotron-ultra-253b-v1": {
            "alias": "nemotron-ultra-253b",
            "provider": "nvidia",
            "latency": "slow",
            "best_for": ["深度研究", "复杂投研"],
        },
        "coordinator-agent/deepseek-ai/deepseek-r1-distill-llama-8b": {
            "alias": "deepseek-r1-8b",
            "provider": "deepseek",
            "latency": "fast",
            "best_for": ["快评推荐", "结构化结论", "低延迟分析"],
        },
        "deepseek-ai/deepseek-r1-distill-llama-8b": {
            "alias": "deepseek-r1-8b",
            "provider": "deepseek",
            "latency": "fast",
            "best_for": ["快评推荐", "结构化结论", "低延迟分析"],
        },
        "coordinator-agent/qwen/qwen3.5-397b-a17b": {
            "alias": "qwen3.5-397b",
            "provider": "qwen",
            "latency": "slow",
            "best_for": ["复杂总结", "高容量上下文"],
        },
        "qwen/qwen3.5-397b-a17b": {
            "alias": "qwen3.5-397b",
            "provider": "qwen",
            "latency": "slow",
            "best_for": ["复杂总结", "高容量上下文"],
        },
        "coordinator-agent/meta/llama-3.2-90b-vision-instruct": {
            "alias": "llama-3.2-90b-vision",
            "provider": "meta",
            "latency": "medium",
            "best_for": ["图像理解", "视觉终审", "多模态洞察"],
        },
        "meta/llama-3.2-90b-vision-instruct": {
            "alias": "llama-3.2-90b-vision",
            "provider": "meta",
            "latency": "medium",
            "best_for": ["图像理解", "视觉终审", "多模态洞察"],
        },
        "coordinator-agent/minimaxai/minimax-m2.5": {
            "alias": "minimax-m2.5",
            "provider": "minimax",
            "latency": "medium",
            "best_for": ["综合助手", "自然语言润色"],
        },
        "minimaxai/minimax-m2.5": {
            "alias": "minimax-m2.5",
            "provider": "minimax",
            "latency": "medium",
            "best_for": ["综合助手", "自然语言润色"],
        },
        "coordinator-agent/minimaxai/minimax-m2.1": {
            "alias": "minimax-m2.1",
            "provider": "minimax",
            "latency": "fast",
            "best_for": ["快速问答", "轻量总结"],
        },
        "minimaxai/minimax-m2.1": {
            "alias": "minimax-m2.1",
            "provider": "minimax",
            "latency": "fast",
            "best_for": ["快速问答", "轻量总结"],
        },
        "coordinator-agent/z-ai/glm4.7": {
            "alias": "glm4.7",
            "provider": "z-ai",
            "latency": "medium",
            "best_for": ["中文表达", "中英文混合分析"],
        },
        "z-ai/glm4.7": {
            "alias": "glm4.7",
            "provider": "z-ai",
            "latency": "medium",
            "best_for": ["中文表达", "中英文混合分析"],
        },
        "nvidia/nemotron-3-super-120b-a12b": {
            "alias": "nemotron-3-super",
            "provider": "nvidia",
            "latency": "medium",
            "best_for": ["兼容兜底", "旧配置回退"],
        },
        "gemma3:12b": {
            "alias": "gemma3-12b",
            "provider": "ollama",
            "latency": "fast",
            "best_for": ["本地低延迟", "脉冲扫描", "云端兜底"],
        },
    }

    TASK_MODEL_KEYS = {
        "scan_pulse": ("AI_MODEL_SCAN_PULSE", "AI_MODEL_SCAN_FAST"),
        "scan_fast": ("AI_MODEL_SCAN_PULSE", "AI_MODEL_SCAN_FAST"),
        "scan_risk": "AI_MODEL_SCAN_RISK",
        "scan_final": "AI_MODEL_SCAN_FINAL",
        "trend_batch": ("AI_MODEL_TREND_BATCH", "AI_MODEL_SCAN_FAST"),
        "recommend_brief": "AI_MODEL_RECOMMEND_BRIEF",
        "recommend_summary": "AI_MODEL_RECOMMEND_SUMMARY",
        "vision": "AI_MODEL_VISION",
        "assistant": ("AI_MODEL_ASSISTANT", "AI_MODEL"),
        "general": "AI_MODEL",
    }

    DEFAULT_MODEL = "gpt-5.5"
    DEFAULT_TASK_MODELS = {
        "scan_pulse": "gpt-5.4",
        "scan_fast": "gpt-5.4",
        "scan_risk": "gpt-5.4",
        "scan_final": "gpt-5.5",
        "trend_batch": "gpt-5.4",
        "recommend_brief": "gpt-5.4",
        "recommend_summary": "gpt-5.5",
        "vision": "gpt-5.4",
        "assistant": "gpt-5.5",
        "general": "gpt-5.5",
    }

    SCAN_TASKS = {"scan_pulse", "scan_fast", "scan_risk", "scan_final"}
    SCAN_QUALITY_TASKS = SCAN_TASKS | {"trend_batch"}
    RECOMMENDATION_TASKS = {"recommend_brief", "recommend_summary"}
    REASONING_EFFORTS = {"minimal", "low", "medium", "high"}

    @staticmethod
    def _is_timeout_error_message(message: str) -> bool:
        normalized = str(message or "").strip().lower()
        return any(
            marker in normalized
            for marker in [
                "gateway timeout",
                "timed out",
                "read timed out",
                "connection refused",
                "connection aborted",
                "connection reset",
                "max retries exceeded",
                "failed to establish a new connection",
                "service unavailable",
                "504",
                "503",
                "sub2api",
                "超时",
                "拒绝连接",
            ]
        )

    @classmethod
    def _build_business_error(cls, detail: str) -> str:
        detail_text = str(detail or "").strip()
        if cls._is_timeout_error_message(detail_text):
            return "AI研判服务超时，请稍后重试"
        return detail_text or "AI研判服务暂时不可用，请稍后重试"

    @classmethod
    def _provider_cooldown_seconds(cls, user_id: int = 1) -> int:
        raw_value = AppConfig.get("AI_PROVIDER_COOLDOWN_SECONDS", user_id=user_id, default=90)
        try:
            return max(0, int(raw_value or 0))
        except (TypeError, ValueError):
            return 90

    @classmethod
    def _provider_failure_threshold(cls, user_id: int = 1) -> int:
        raw_value = AppConfig.get("AI_PROVIDER_COOLDOWN_FAILURES", user_id=user_id, default=1)
        try:
            return max(1, int(raw_value or 1))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _provider_cooldown_key(provider_name: str, task: str, user_id: int) -> str:
        return f"{int(user_id)}:{provider_name}:{task}"

    @classmethod
    def _uses_provider_cooldown(cls, task: str) -> bool:
        return task in cls.RECOMMENDATION_TASKS

    @classmethod
    def _provider_inflight_ttl_seconds(cls, user_id: int = 1) -> int:
        raw_value = AppConfig.get("AI_PROVIDER_INFLIGHT_TTL_SECONDS", user_id=user_id, default=150)
        try:
            return max(15, int(raw_value or 150))
        except (TypeError, ValueError):
            return 150

    @classmethod
    def _try_begin_provider_request(cls, provider_name: str, task: str, user_id: int = 1) -> bool:
        if not cls._uses_provider_cooldown(task):
            return True

        key = cls._provider_cooldown_key(provider_name, task, user_id)
        now = time.time()
        with cls._provider_cooldown_lock:
            expires_at = float(cls._provider_inflight.get(key) or 0)
            if expires_at > now:
                return False
            cls._provider_inflight[key] = now + cls._provider_inflight_ttl_seconds(user_id=user_id)
            return True

    @classmethod
    def _end_provider_request(cls, provider_name: str, task: str, user_id: int = 1) -> None:
        if not cls._uses_provider_cooldown(task):
            return
        key = cls._provider_cooldown_key(provider_name, task, user_id)
        with cls._provider_cooldown_lock:
            cls._provider_inflight.pop(key, None)

    @classmethod
    def _provider_cooldown_remaining(cls, provider_name: str, task: str, user_id: int = 1) -> float:
        if not cls._uses_provider_cooldown(task):
            return 0.0
        key = cls._provider_cooldown_key(provider_name, task, user_id)
        with cls._provider_cooldown_lock:
            state = cls._provider_failures.get(key) or {}
            cooldown_until = float(state.get("cooldown_until") or 0)
        return max(0.0, cooldown_until - time.time())

    @classmethod
    def _record_provider_success(cls, provider_name: str, task: str, user_id: int = 1) -> None:
        if not cls._uses_provider_cooldown(task):
            return
        key = cls._provider_cooldown_key(provider_name, task, user_id)
        with cls._provider_cooldown_lock:
            cls._provider_failures.pop(key, None)

    @classmethod
    def _record_provider_failure(cls, provider_name: str, task: str, detail: str, user_id: int = 1) -> None:
        if not cls._uses_provider_cooldown(task) or not cls._is_timeout_error_message(detail):
            return
        cooldown_seconds = cls._provider_cooldown_seconds(user_id=user_id)
        if cooldown_seconds <= 0:
            return

        threshold = cls._provider_failure_threshold(user_id=user_id)
        key = cls._provider_cooldown_key(provider_name, task, user_id)
        with cls._provider_cooldown_lock:
            current = dict(cls._provider_failures.get(key) or {})
            failure_count = int(current.get("failure_count") or 0) + 1
            cooldown_until = float(current.get("cooldown_until") or 0)
            if failure_count >= threshold:
                cooldown_until = time.time() + cooldown_seconds
            cls._provider_failures[key] = {
                "failure_count": failure_count,
                "cooldown_until": cooldown_until,
                "last_error": str(detail or "")[:240],
                "last_failure_at": time.time(),
            }

        if failure_count >= threshold:
            MonitorLink.log(
                f"⚠️ [AI] {provider_name} provider cooldown activated for {task}: "
                f"{cooldown_seconds}s after {failure_count} failures"
            )

    @classmethod
    def _safe_scan_fallback(cls, task: str) -> str | None:
        if task == "scan_pulse":
            return (
                "趋势判断: 服务超时，沿用指标快照\n"
                "指标共振: 已切换到本地指标判断\n"
                "大盘联动: 当前使用最近一次市场快照\n"
                "机会窗口: 等待服务恢复后复核\n"
                "一句结论: AI 服务超时，先展示降级研判结果。\n"
                "建议标签: HOLD"
            )
        if task == "scan_risk":
            return (
                "情绪温度: 中性\n"
                "资金流与波动: 使用本地快照继续评估\n"
                "主要风险: AI 服务超时，需人工复核\n"
                "仓位建议: 控制仓位\n"
                "市场环境: 当前展示最近市场快照\n"
                "一句结论: 风险层已降级为本地风控结论。\n"
                "建议标签: HOLD"
            )
        if task == "scan_final":
            return (
                "趋势判断: 当前以本地快照继续输出\n"
                "关键指标: 待 AI 服务恢复后复核细节\n"
                "市场扫描: 当前采用最近一次市场快照\n"
                "操作策略: 暂不扩大仓位，等待复核\n"
                "目标价位: $0.00\n"
                "止损价位: $0.00\n"
                "基本面评分: 6.0/10\n"
                "技术面评分: 6.0/10\n"
                "资金面评分: 6.0/10\n"
                "大盘共振评分: 6.0/10\n"
                "综合置信度: 35%\n"
                "最终决策: HOLD\n"
                "详细理由: AI研判服务超时，系统已切换为本地降级结果，请稍后重试。"
            )
        return None

    TASK_FALLBACK_MODELS = {
        "scan_pulse": ["gpt-5.4", "gpt-5.5"],
        "scan_fast": ["gpt-5.4", "gpt-5.5"],
        "scan_risk": ["gpt-5.4", "gpt-5.5"],
        "scan_final": ["gpt-5.5", "gpt-5.4"],
        "trend_batch": ["gpt-5.4", "gpt-5.5"],
        "recommend_brief": ["gpt-5.4", "gpt-5.5"],
        "recommend_summary": ["gpt-5.5", "gpt-5.4"],
        "vision": ["gpt-5.4", "gpt-5.5"],
        "assistant": ["gpt-5.5", "gpt-5.4"],
        "general": ["gpt-5.5", "gpt-5.4"],
    }

    @classmethod
    def _uses_official_nvidia_catalog(cls, user_id: int = 1) -> bool:
        legacy_url = (AppConfig.get("AI_URL", user_id=user_id, default="") or "").strip().lower()
        base_url = (AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "").strip().lower()
        return "integrate.api.nvidia.com" in legacy_url or "integrate.api.nvidia.com" in base_url

    @classmethod
    def _canonical_cloud_model_id(cls, model_id: str) -> str:
        normalized = str(model_id or "").strip()
        if not normalized:
            return ""
        if normalized in cls.MODEL_ID_ALIASES:
            return cls.MODEL_ID_ALIASES[normalized]
        if normalized.startswith("coordinator-agent/"):
            normalized = normalized.replace("coordinator-agent/", "", 1)
        return cls.MODEL_ID_ALIASES.get(normalized, normalized)

    @classmethod
    def normalize_ai_config_map(cls, config_map: dict[str, object]) -> dict[str, object]:
        payload = dict(config_map or {})
        normalized = dict(payload)
        for field in cls.CONFIG_MODEL_FIELDS:
            raw_value = payload.get(field)
            if raw_value:
                normalized[field] = cls._canonical_cloud_model_id(str(raw_value))

        base_url = str(payload.get("ai_base_url") or "").strip().rstrip("/")
        ai_url = str(payload.get("ai_url") or "").strip()
        if base_url and ("integrate.api.nvidia.com" in base_url.lower() or "sub2api" in base_url.lower()):
            normalized["ai_base_url"] = base_url
            normalized["ai_url"] = f"{base_url}/chat/completions"
            normalized["ai_api_style"] = "openai-chat-completions"
        elif ai_url and "integrate.api.nvidia.com" in ai_url.lower():
            normalized["ai_url"] = (
                ai_url.replace("/completions", "/chat/completions")
                if ai_url.endswith("/completions") and not ai_url.endswith("/chat/completions")
                else ai_url
            )
        return normalized

    @classmethod
    def migrate_user_ai_settings(cls, user_id: int = 1) -> dict[str, object]:
        current = AppConfig.get_all(user_id)
        normalized = cls.normalize_ai_config_map(current)
        changed = {}
        for key, value in normalized.items():
            if current.get(key) != value:
                AppConfig.set(key.upper(), value, user_id=user_id, description=f"自动迁移 {key}")
                changed[key] = value
        return {"changed": changed, "changedCount": len(changed), "configs": {**current, **normalized}}

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        normalized = str(provider or "").strip().lower()
        if normalized in {"ollama", "local"}:
            return "ollama"
        if normalized in {"nvidia", "openai", "sub2api", "openai-compatible", "openai_chat"}:
            return "nvidia"
        if normalized in {"hybrid"}:
            return normalized
        return ""

    @classmethod
    def _provider(cls, user_id: int = 1) -> str:
        provider = cls._normalize_provider(AppConfig.get("AI_PROVIDER", user_id=user_id, default=""))
        if provider:
            return provider

        url = (AppConfig.get("AI_URL", user_id=user_id, default="") or "").strip().lower()
        base_url = (AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "").strip().lower()
        if any(marker in url or marker in base_url for marker in ("integrate.api.nvidia.com", "sub2api", "/v1")):
            return "nvidia"
        return "ollama"

    @classmethod
    def _fallback_provider(cls, user_id: int = 1) -> str:
        configured = cls._normalize_provider(AppConfig.get("AI_FALLBACK_PROVIDER", user_id=user_id, default=""))
        if configured:
            return configured

        primary = cls._provider(user_id=user_id)
        return "ollama" if primary == "nvidia" and cls._fallback_enabled(user_id=user_id) else ""

    @staticmethod
    def _fallback_enabled(user_id: int = 1) -> bool:
        raw = AppConfig.get("AI_FALLBACK_PROVIDER", user_id=user_id, default="")
        return bool(str(raw or "").strip())

    @staticmethod
    def _local_url(user_id: int = 1) -> str:
        return (
            AppConfig.get("AI_LOCAL_URL", user_id=user_id, default="")
            or AppConfig.get("AI_URL", user_id=user_id, default="")
            or "http://127.0.0.1:11434/api/generate"
        ).strip()

    @staticmethod
    def _preferred_local_model(user_id: int = 1) -> str:
        configured = (AppConfig.get("AI_LOCAL_MODEL", user_id=user_id, default="") or "").strip()
        return configured or "gemma3:12b"

    @classmethod
    def _available_local_models(cls, user_id: int = 1) -> list[str]:
        now = time.time()
        cached_models = cls._ollama_models_cache.get("models") or []
        if cached_models and (now - float(cls._ollama_models_cache.get("at") or 0)) < 60:
            return list(cached_models)

        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(cls._local_url(user_id=user_id).replace("/api/generate", "/api/tags"), timeout=3)
            if response.status_code == 200:
                payload = response.json() or {}
                models = [
                    (item.get("model") or item.get("name") or "").strip()
                    for item in payload.get("models", [])
                    if (item.get("model") or item.get("name"))
                ]
                cls._ollama_models_cache = {"at": now, "models": models}
                return models
        except Exception:
            pass
        return list(cached_models)

    @classmethod
    def _local_model(cls, user_id: int = 1) -> str:
        preferred = cls._preferred_local_model(user_id=user_id)
        available = cls._available_local_models(user_id=user_id)
        if not available:
            return preferred
        if preferred in available:
            return preferred
        for candidate in ["llama-fast:latest", "llama3.1:8b", "gemma3:12b"]:
            if candidate in available:
                return candidate
        return available[0]

    @staticmethod
    def _local_timeout(user_id: int = 1) -> int:
        return int(AppConfig.get("AI_LOCAL_TIMEOUT", user_id=user_id, default=45) or 45)

    @classmethod
    def _provider_order(cls, task: str = "general", user_id: int = 1) -> list[str]:
        primary = cls._provider(user_id=user_id)
        fallback = cls._fallback_provider(user_id=user_id)

        if primary == "hybrid":
            # 混合模式下仅对极低时延的轻任务优先走本地，大多数用户可感知任务优先云端。
            local_first_tasks = {"scan_pulse", "scan_fast"}
            ordered = ["ollama", "nvidia"] if task in local_first_tasks else ["nvidia", "ollama"]
        else:
            ordered = [primary]
            if fallback and fallback != primary:
                ordered.append(fallback)

        deduped = []
        for provider_name in ordered:
            normalized = cls._normalize_provider(provider_name)
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped or ["ollama"]

    @staticmethod
    def _timeout(user_id: int = 1) -> int:
        try:
            return max(1, int(AppConfig.get("AI_TIMEOUT", user_id=user_id, default=8) or 8))
        except (TypeError, ValueError):
            return 8

    @staticmethod
    def _temperature(user_id: int = 1) -> float:
        return float(AppConfig.get("TEMPERATURE", user_id=user_id, default=0.2) or 0.2)

    @classmethod
    def _reasoning_effort_for_task(cls, task: str, user_id: int = 1) -> str:
        key = "AI_SCAN_REASONING_EFFORT" if task in cls.SCAN_QUALITY_TASKS else "AI_REASONING_EFFORT"
        default_effort = "high" if task in cls.SCAN_QUALITY_TASKS else "medium"
        configured = str(AppConfig.get(key, user_id=user_id, default=default_effort) or default_effort).strip().lower()
        return configured if configured in cls.REASONING_EFFORTS else default_effort

    @classmethod
    def _quality_label_for_task(cls, task: str, user_id: int = 1) -> str:
        effort = cls._reasoning_effort_for_task(task, user_id=user_id)
        return {"minimal": "最低质量", "low": "低质量", "medium": "标准质量", "high": "最高质量"}.get(
            effort, "标准质量"
        )

    @staticmethod
    def _max_tokens(user_id: int = 1) -> int:
        return int(AppConfig.get("NUM_PREDICT", user_id=user_id, default=900) or 900)

    @classmethod
    def _max_tokens_for_task(cls, task: str, user_id: int = 1) -> int:
        base_tokens = cls._max_tokens(user_id=user_id)
        if task in {"scan_pulse", "scan_fast", "scan_risk", "recommend_brief"}:
            return min(base_tokens, 180)
        if task == "trend_batch":
            return min(max(base_tokens, 720), 1400)
        if task in {"scan_final", "recommend_summary"}:
            return min(base_tokens, 320)
        if task == "vision":
            return min(base_tokens, 300)
        if task == "assistant":
            return min(max(base_tokens, 900), 1400)
        return base_tokens

    @classmethod
    def _request_timeout_for_task(cls, task: str, user_id: int = 1, provider: str | None = None) -> int:
        base_timeout = cls._timeout(user_id=user_id)
        target_provider = cls._normalize_provider(provider) or cls._provider(user_id=user_id)
        if target_provider == "nvidia":
            if task in {"scan_pulse", "scan_fast", "scan_risk", "recommend_brief"}:
                return min(base_timeout, 8)
            if task == "trend_batch":
                return min(max(base_timeout, 6), 12)
            if task in {"scan_final", "recommend_summary", "vision", "general"}:
                return min(max(base_timeout, 6), 12)
            if task == "assistant":
                return min(max(base_timeout, 24), 45)
            return min(base_timeout, 8)
        if task in {"scan_pulse", "scan_fast", "scan_risk", "recommend_brief"}:
            return min(base_timeout, 8)
        if task == "trend_batch":
            return min(max(base_timeout, 16), 24)
        if task in {"scan_final", "recommend_summary"}:
            return min(base_timeout, 12)
        if task == "vision":
            return min(base_timeout, 12)
        if task == "assistant":
            return min(max(base_timeout, 24), 45)
        return base_timeout

    @staticmethod
    def _nvidia_endpoints(user_id: int = 1) -> list[str]:
        legacy_url = (AppConfig.get("AI_URL", user_id=user_id, default="") or "").strip()
        base_url = (AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "").strip()
        api_style = (
            (AppConfig.get("AI_API_STYLE", user_id=user_id, default="openai-completions") or "openai-completions")
            .strip()
            .lower()
        )
        is_official_nvidia = (
            "integrate.api.nvidia.com" in legacy_url.lower() or "integrate.api.nvidia.com" in base_url.lower()
        )
        prefer_chat = is_official_nvidia or api_style not in {"openai-completions", "completions"}
        if legacy_url.endswith("/chat/completions"):
            prefer_chat = True
        elif legacy_url.endswith("/completions"):
            prefer_chat = True if is_official_nvidia else False

        endpoints: list[str] = []
        if legacy_url:
            if legacy_url.endswith("/chat/completions"):
                endpoints.append(legacy_url)
                if api_style in {"openai-completions", "completions"}:
                    endpoints.append(legacy_url.replace("/chat/completions", "/completions"))
            elif legacy_url.endswith("/completions"):
                if prefer_chat:
                    endpoints.extend([legacy_url.replace("/completions", "/chat/completions"), legacy_url])
                else:
                    endpoints.extend([legacy_url, legacy_url.replace("/completions", "/chat/completions")])
            else:
                endpoints.append(legacy_url)

        if base_url:
            normalized_base = base_url.rstrip("/")
            if prefer_chat:
                endpoints.extend([f"{normalized_base}/chat/completions", f"{normalized_base}/completions"])
            elif api_style in {"openai-completions", "completions"}:
                endpoints.extend([f"{normalized_base}/completions", f"{normalized_base}/chat/completions"])
            else:
                endpoints.extend([f"{normalized_base}/chat/completions", f"{normalized_base}/completions"])

        if not endpoints:
            endpoints = [
                "https://integrate.api.nvidia.com/v1/completions",
                "https://integrate.api.nvidia.com/v1/chat/completions",
            ]

        deduped = []
        for endpoint in endpoints:
            if endpoint and endpoint not in deduped:
                deduped.append(endpoint)
        return deduped

    @classmethod
    def _respect_nvidia_rate_limit(cls, max_calls_per_minute: int = 38) -> None:
        with cls._nvidia_rate_lock:
            now = time.time()
            cls._nvidia_call_times = [stamp for stamp in cls._nvidia_call_times if (now - stamp) < 60]
            if len(cls._nvidia_call_times) >= max_calls_per_minute:
                wait_seconds = max(0.5, 60 - (now - cls._nvidia_call_times[0]))
                MonitorLink.log(f"⏳ [AI] 命中 NVIDIA 频率保护，等待 {wait_seconds:.1f} 秒")
                time.sleep(wait_seconds)
                now = time.time()
                cls._nvidia_call_times = [stamp for stamp in cls._nvidia_call_times if (now - stamp) < 60]
            cls._nvidia_call_times.append(time.time())

    @classmethod
    def _resolve_model(
        cls, requested_model: str | None = None, task: str = "general", user_id: int = 1, provider: str | None = None
    ) -> str:
        if requested_model:
            return cls._normalize_model_for_provider(str(requested_model).strip(), user_id=user_id, provider=provider)

        config_keys = cls.TASK_MODEL_KEYS.get(task, "AI_MODEL")
        if not isinstance(config_keys, (list, tuple)):
            config_keys = [config_keys]

        for config_key in config_keys:
            configured = (AppConfig.get(config_key, user_id=user_id, default="") or "").strip()
            if configured:
                return cls._normalize_model_for_provider(configured, user_id=user_id, provider=provider)

        generic = (AppConfig.get("AI_MODEL", user_id=user_id, default="") or "").strip()
        if generic:
            return cls._normalize_model_for_provider(generic, user_id=user_id, provider=provider)

        return cls._normalize_model_for_provider(
            cls.DEFAULT_TASK_MODELS.get(task) or cls.DEFAULT_MODEL, user_id=user_id, provider=provider
        )

    @classmethod
    def _normalize_model_for_provider(cls, model_id: str, user_id: int = 1, provider: str | None = None) -> str:
        resolved = str(model_id or "").strip()
        target_provider = cls._normalize_provider(provider) or cls._provider(user_id=user_id)

        if target_provider == "ollama":
            if not resolved or "/" in resolved:
                return cls._local_model(user_id=user_id)
            return resolved

        resolved = cls._canonical_cloud_model_id(resolved)
        if not resolved:
            return cls.DEFAULT_MODEL

        provider = cls._provider(user_id=user_id)
        base_url = (AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "").strip().lower()

        if provider not in {"nvidia", "hybrid"} and "integrate.api.nvidia.com" not in base_url:
            return resolved

        if cls._uses_official_nvidia_catalog(user_id=user_id) and resolved.startswith("coordinator-agent/"):
            return resolved.replace("coordinator-agent/", "", 1)

        return resolved

    @classmethod
    def _model_candidates(
        cls, requested_model: str | None, task: str = "general", user_id: int = 1, provider: str | None = None
    ) -> list[str]:
        candidates: list[str] = []
        target_provider = cls._normalize_provider(provider) or cls._provider(user_id=user_id)

        def add_candidate(model_id: str | None) -> None:
            normalized = cls._normalize_model_for_provider(model_id or "", user_id=user_id, provider=target_provider)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

        add_candidate(requested_model)
        add_candidate(cls._resolve_model(requested_model, task, user_id=user_id, provider=target_provider))
        if target_provider == "ollama":
            add_candidate(cls._local_model(user_id=user_id))
        else:
            for fallback in cls.TASK_FALLBACK_MODELS.get(task, []):
                add_candidate(fallback)
            add_candidate(cls._resolve_model(None, "general", user_id=user_id, provider=target_provider))
        if task in {"scan_pulse", "scan_fast", "scan_risk", "recommend_brief"}:
            return candidates[:2]
        if task == "trend_batch":
            return candidates[:3]
        if task in {"scan_final", "recommend_summary", "vision"}:
            return candidates[:3]
        return candidates[:2]

    @staticmethod
    def _extract_openai_content(payload: dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""

        first_choice = choices[0] or {}
        message = first_choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            return "".join(
                item.get("text") or item.get("content") or "" for item in content if isinstance(item, dict)
            ).strip()
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            return str(content.get("text") or content.get("content") or "").strip()

        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if isinstance(reasoning, list):
            return "".join(
                item.get("text") or item.get("content") or "" for item in reasoning if isinstance(item, dict)
            ).strip()
        if isinstance(reasoning, dict):
            return str(reasoning.get("text") or reasoning.get("content") or "").strip()
        if isinstance(reasoning, str):
            return reasoning.strip()

        text = first_choice.get("text")
        if isinstance(text, list):
            return "".join(
                item.get("text") or item.get("content") or "" for item in text if isinstance(item, dict)
            ).strip()
        return text.strip() if isinstance(text, str) else ""

    @classmethod
    def get_model_catalog(cls, user_id: int = 1) -> list[dict[str, object]]:
        provider = cls._provider(user_id=user_id)
        provider_order = cls._provider_order(user_id=user_id)
        base_url = (AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "").strip().lower()
        is_openai_gateway = provider == "nvidia" or "integrate.api.nvidia.com" in base_url or "sub2api" in base_url
        local_model = cls._local_model(user_id=user_id)
        catalog = []
        catalog_ids = list(cls.OFFICIAL_CLOUD_MODEL_IDS)
        if local_model not in catalog_ids:
            catalog_ids.append(local_model)

        for model_id in catalog_ids:
            meta = cls.MODEL_CATALOG.get(model_id, {})
            available = True
            availability_note = ""
            if meta.get("provider") == "ollama":
                available = "ollama" in provider_order
                if available:
                    availability_note = "本地 Ollama 通道可用，适合低时延任务。"
                else:
                    availability_note = "当前未启用本地 Ollama 通道。"
            elif is_openai_gateway:
                available = meta.get("provider") != "ollama"
                if not available:
                    availability_note = "当前模型不在已登记的网关路由中。"
            catalog.append(
                {
                    "id": model_id,
                    "alias": meta.get("alias") or model_id,
                    "provider": meta.get("provider") or ("ollama" if model_id == local_model else "unknown"),
                    "latency": meta.get("latency") or ("fast" if model_id == local_model else "medium"),
                    "best_for": meta.get("best_for", []),
                    "available": available,
                    "availabilityNote": availability_note,
                    "official": model_id in cls.OFFICIAL_CLOUD_MODEL_IDS,
                }
            )
        return catalog

    @classmethod
    def _build_nvidia_payload(
        cls, endpoint: str, prompt: str, target_model: str, task: str = "general", user_id: int = 1
    ) -> dict:
        reasoning_effort = cls._reasoning_effort_for_task(task, user_id=user_id)
        base_payload = {
            "model": target_model,
            "temperature": cls._temperature(user_id=user_id),
            "max_tokens": cls._max_tokens_for_task(task, user_id=user_id),
            "reasoning_effort": reasoning_effort,
            "stream": False,
        }
        if endpoint.endswith("/chat/completions"):
            return {**base_payload, "messages": [{"role": "user", "content": prompt}]}
        return {**base_payload, "prompt": prompt}

    @classmethod
    def get_model_meta(cls, model_id: str | None, user_id: int = 1) -> dict[str, object]:
        resolved_id = cls._canonical_cloud_model_id(str(model_id or "").strip())
        meta = cls.MODEL_CATALOG.get(resolved_id, {})
        if not meta and resolved_id == cls._local_model(user_id=user_id):
            meta = {
                "alias": resolved_id,
                "provider": "ollama",
                "latency": "fast",
                "best_for": ["本地模型", "低时延兜底"],
            }
        alias = meta.get("alias") or resolved_id or "unknown-model"
        return {
            "id": resolved_id,
            "alias": alias,
            "provider": meta.get("provider") or "unknown",
            "latency": meta.get("latency") or "medium",
            "quality": "标准质量",
            "reasoningEffort": "medium",
            "best_for": meta.get("best_for", []),
        }

    @classmethod
    def get_task_model_plan(cls, user_id: int = 1) -> dict[str, dict[str, object]]:
        def meta_for(task_name: str) -> dict[str, object]:
            provider_name = cls._provider_order(task=task_name, user_id=user_id)[0]
            model_meta = cls.get_model_meta(
                cls._resolve_model(task=task_name, user_id=user_id, provider=provider_name), user_id=user_id
            )
            return {
                **model_meta,
                "quality": cls._quality_label_for_task(task_name, user_id=user_id),
                "reasoningEffort": cls._reasoning_effort_for_task(task_name, user_id=user_id),
                "providerRoute": provider_name,
            }

        return {
            "pulse": meta_for("scan_pulse"),
            "trendBatch": meta_for("trend_batch"),
            "risk": meta_for("scan_risk"),
            "final": meta_for("scan_final"),
            "recommendBrief": meta_for("recommend_brief"),
            "recommendSummary": meta_for("recommend_summary"),
            "vision": meta_for("vision"),
            "general": meta_for("general"),
        }

    @classmethod
    def get_task_provider_plan(cls, user_id: int = 1) -> dict[str, dict[str, object]]:
        tasks = {
            "pulse": "scan_pulse",
            "trendBatch": "trend_batch",
            "risk": "scan_risk",
            "final": "scan_final",
            "recommendBrief": "recommend_brief",
            "recommendSummary": "recommend_summary",
            "vision": "vision",
            "general": "general",
        }
        return {
            name: {"primary": order[0], "fallbacks": order[1:]}
            for name, task_name in tasks.items()
            for order in [cls._provider_order(task=task_name, user_id=user_id)]
        }

    @classmethod
    def probe_connection(cls, config_map: dict[str, object] | None = None, user_id: int = 1) -> dict[str, object]:
        config = cls.normalize_ai_config_map(config_map or {})
        provider = cls._normalize_provider(config.get("ai_provider")) or cls._provider(user_id=user_id)
        fallback_provider = cls._normalize_provider(config.get("ai_fallback_provider"))
        provider_order = ["nvidia", "ollama"] if provider == "hybrid" else [provider]
        if fallback_provider and fallback_provider not in provider_order:
            provider_order.append(fallback_provider)

        api_key = str(
            config.get("ai_api_key") or AppConfig.get("AI_API_KEY", user_id=user_id, default="") or ""
        ).strip()
        base_url = (
            str(config.get("ai_base_url") or AppConfig.get("AI_BASE_URL", user_id=user_id, default="") or "")
            .strip()
            .rstrip("/")
        )
        local_url = str(
            config.get("ai_local_url") or AppConfig.get("AI_LOCAL_URL", user_id=user_id, default="") or ""
        ).strip()
        cloud_model = cls._canonical_cloud_model_id(
            str(
                config.get("ai_model")
                or AppConfig.get("AI_MODEL", user_id=user_id, default=cls.DEFAULT_MODEL)
                or cls.DEFAULT_MODEL
            )
        )
        local_model = str(
            config.get("ai_local_model")
            or AppConfig.get("AI_LOCAL_MODEL", user_id=user_id, default=cls._preferred_local_model(user_id=user_id))
            or ""
        ).strip() or cls._preferred_local_model(user_id=user_id)
        session = requests.Session()
        session.trust_env = False
        last_error = "未执行连接测试"

        for target_provider in provider_order:
            if target_provider == "nvidia":
                if not base_url or not cloud_model:
                    last_error = "缺少 Base URL 或默认模型"
                    continue

                headers = {"Content-Type": "application/json", "Accept": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                endpoint = f"{base_url}/chat/completions"
                payload = {
                    "model": cloud_model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 12,
                    "temperature": 0,
                    "stream": False,
                    "reasoning_effort": "low",
                }
                try:
                    response = session.post(endpoint, json=payload, headers=headers, timeout=20)
                    if response.status_code == 200:
                        content = cls._extract_openai_content(response.json() or {})
                        return {
                            "success": True,
                            "provider": "nvidia",
                            "endpoint": endpoint,
                            "model": cloud_model,
                            "message": content or "Sub2API 路由连接成功",
                        }
                    last_error = f"OpenAI-compatible 请求失败: {response.status_code} {response.text[:180]}"
                except Exception as exc:
                    last_error = cls._build_business_error(str(exc))
                continue

            if target_provider == "ollama":
                if not local_url or not local_model:
                    last_error = "缺少本地模型地址或本地模型名称"
                    continue

                payload = {
                    "model": local_model,
                    "prompt": "Reply with OK.",
                    "stream": False,
                    "options": {"num_predict": 12, "temperature": 0},
                }
                try:
                    response = session.post(
                        local_url, json=payload, timeout=min(cls._local_timeout(user_id=user_id), 20)
                    )
                    if response.status_code == 200:
                        body = response.json() or {}
                        return {
                            "success": True,
                            "provider": "ollama",
                            "endpoint": local_url,
                            "model": local_model,
                            "message": (body.get("response") or "").strip() or "本地模型连接成功",
                        }
                    last_error = f"Ollama 请求失败: {response.status_code} {response.text[:180]}"
                except Exception as exc:
                    last_error = cls._build_business_error(str(exc))

        return {
            "success": False,
            "provider": provider_order[0] if provider_order else provider,
            "endpoint": f"{base_url}/chat/completions" if base_url else local_url,
            "model": cloud_model if provider_order and provider_order[0] == "nvidia" else local_model,
            "message": last_error or "AI 连接测试失败",
        }

    @classmethod
    def _request_nvidia(cls, prompt: str, model: str | None, task: str = "general", user_id: int = 1) -> str:
        api_key = (AppConfig.get("AI_API_KEY", user_id=user_id, default="") or "").strip()
        if not api_key:
            MonitorLink.log("⚠️ [AI] 未配置 AI_API_KEY，无法调用 OpenAI-compatible 网关")
            return "ERROR: 未配置 AI_API_KEY"

        endpoints = cls._nvidia_endpoints(user_id=user_id)
        model_candidates = cls._model_candidates(model, task=task, user_id=user_id, provider="nvidia")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        session = requests.Session()
        session.trust_env = False
        max_attempts = 2
        endpoint_not_found = False

        for target_model in model_candidates:
            not_found_count = 0
            for url in endpoints:
                payload = cls._build_nvidia_payload(url, prompt, target_model, task=task, user_id=user_id)
                MonitorLink.log(f"🔗 [AI] OpenAI-compatible 请求: {target_model} (task={task})")
                MonitorLink.log(f"🔗 [AI] 请求地址: {url}")

                last_status = None
                for attempt in range(max_attempts):
                    try:
                        cls._respect_nvidia_rate_limit()
                        response = session.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=cls._request_timeout_for_task(task, user_id=user_id, provider="nvidia"),
                        )
                        if response.status_code == 200:
                            response_payload = response.json()
                            content = cls._extract_openai_content(response_payload)
                            if content:
                                return content
                            last_status = 408
                            MonitorLink.log(
                                f"⚠️ [AI] OpenAI-compatible 返回空内容: model={target_model} "
                                f"choices={len(response_payload.get('choices') or [])} "
                                f"body={str(response_payload)[:280]}"
                            )
                            continue

                        last_status = response.status_code
                        MonitorLink.log(
                            f"⚠️ [AI] OpenAI-compatible 请求失败: {response.status_code} {response.text[:240]}"
                        )
                        if response.status_code == 404 and "page not found" in response.text.lower():
                            not_found_count += 1
                            break
                        if response.status_code in {404, 405, 408, 429}:
                            break
                        if 400 <= response.status_code < 500:
                            break
                    except Exception as exc:
                        last_status = 408
                        if cls._is_timeout_error_message(str(exc)):
                            MonitorLink.log(
                                f"⚠️ [AI] OpenAI-compatible provider timeout handled: "
                                f"model={target_model} task={task}"
                            )
                            return f"ERROR: {cls._build_business_error(str(exc))}"
                        MonitorLink.log(f"⚠️ [AI] OpenAI-compatible 调用异常: {exc}")
                        time.sleep(0.5)

                if last_status not in {404, 405, 408, 429}:
                    break

            if not_found_count >= len(endpoints):
                endpoint_not_found = True
                break

        if endpoint_not_found:
            return "ERROR: OpenAI-compatible 网关返回 404，请检查 AI_BASE_URL、AI_URL 或模型路由权限"

        if last_status == 504:
            return f"ERROR: {cls._build_business_error('504 Gateway Timeout')}"
        return f"ERROR: {cls._build_business_error('OpenAI-compatible 请求失败，请检查模型配置或接口地址')}"

    @classmethod
    def _request_ollama(cls, prompt: str, model: str | None, task: str = "general", user_id: int = 1) -> str:
        target_model = cls._resolve_model(model, task, user_id=user_id, provider="ollama")
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_thread": int(AppConfig.get("NUM_THREAD", user_id=user_id, default=4) or 4),
                "temperature": cls._temperature(user_id=user_id),
                "num_predict": cls._max_tokens_for_task(task, user_id=user_id),
            },
        }

        url = cls._local_url(user_id=user_id)
        MonitorLink.log(f"🔗 [AI] Ollama 请求: {target_model} (task={task})")
        MonitorLink.log(f"🔗 [AI] 请求地址: {url}")

        session = requests.Session()
        session.trust_env = False
        for attempt in range(2):
            try:
                response = session.post(url, json=payload, timeout=cls._local_timeout(user_id=user_id))
                if response.status_code == 200:
                    result = (response.json() or {}).get("response", "").strip()
                    if result:
                        return result
                else:
                    MonitorLink.log(f"⚠️ [AI] Ollama 请求失败: {response.status_code}")
            except Exception as exc:
                MonitorLink.log(f"⚠️ [AI] Ollama 调用异常: {exc}")
                time.sleep(1.5)

        return "ERROR"

    @classmethod
    def get_decision(cls, model: str | None, prompt: str, task: str = "general", user_id: int = 1) -> str:
        """统一 AI 调用接口，支持按任务路由模型。"""
        last_error = "ERROR"
        for provider_name in cls._provider_order(task=task, user_id=user_id):
            cooldown_remaining = cls._provider_cooldown_remaining(provider_name, task=task, user_id=user_id)
            if cooldown_remaining > 0:
                last_error = f"ERROR: {provider_name} provider cooling down for {cooldown_remaining:.0f}s"
                MonitorLink.log(
                    f"⚠️ [AI] 跳过 {provider_name} provider: task={task} "
                    f"cooldown_remaining={cooldown_remaining:.0f}s"
                )
                continue

            if not cls._try_begin_provider_request(provider_name, task=task, user_id=user_id):
                last_error = f"ERROR: {provider_name} provider request already in flight"
                MonitorLink.log(f"⚠️ [AI] 跳过 {provider_name} provider: task={task} request_inflight=true")
                continue

            try:
                if provider_name == "nvidia":
                    result = cls._request_nvidia(prompt, model, task=task, user_id=user_id)
                else:
                    result = cls._request_ollama(prompt, model, task=task, user_id=user_id)
            finally:
                cls._end_provider_request(provider_name, task=task, user_id=user_id)

            if result and not str(result).startswith("ERROR"):
                cls._record_provider_success(provider_name, task=task, user_id=user_id)
                return result
            last_error = result or last_error
            cls._record_provider_failure(provider_name, task=task, detail=last_error, user_id=user_id)

        if task in cls.SCAN_TASKS and cls._is_timeout_error_message(last_error):
            fallback = cls._safe_scan_fallback(task)
            if fallback:
                MonitorLink.log(f"⚠️ [AI] {task} 超时，返回安全降级结果")
                return fallback

        return last_error

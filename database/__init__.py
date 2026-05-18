from __future__ import annotations
import logging
import sys
from pathlib import Path

# 初始化日志，方便追踪重构过程中的加载问题
_logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_LEGACY_DIR = _PACKAGE_ROOT / "backend-server" / "src" / "database"

if not _LEGACY_DIR.exists():
    _logger.warning(f"Legacy database directory not found at: {_LEGACY_DIR}")
else:
    # 将旧目录添加到包搜索路径，允许作为此包的一部分进行导入
    if str(_LEGACY_DIR) not in __path__:
        __path__.append(str(_LEGACY_DIR))

    _legacy_init = _LEGACY_DIR / "__init__.py"
    if _legacy_init.exists():
        try:
            # 使用 exec 将旧代码的命名空间注入到当前模块
            # compile 能够提供更好的错误堆栈信息（保留文件名）
            _code = compile(_legacy_init.read_text(encoding="utf-8"), str(_legacy_init), "exec")
            exec(_code, globals())
        except Exception as e:
            _logger.error(f"Failed to execute legacy database __init__.py: {e}", exc_info=True)
            # 如果数据库初始化失败是致命的，可以考虑重新抛出异常
            # raise

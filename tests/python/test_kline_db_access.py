"""Tests for KLineDataFetcher DB access consolidation.

Verifies:
- KLineDataFetcher no longer holds a bare pymysql.connect
- All DB operations go through DbUtil (which uses DatabasePool)
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

# Ensure the project root is on sys.path so apps.runtime_shared resolves
ROOT = Path(__file__).resolve().parents[2]  # platform-core
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_module(name: str, file_path: str):
    """Load a Python module from a file path (handles hyphenated package dirs)."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    assert spec is not None and spec.loader is not None, f"Cannot load module from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestKLineDataFetcherDBAccess:
    """KLineDataFetcher should not use bare pymysql.connect."""

    @staticmethod
    def _load_kline_fetcher():
        kb_path = str(ROOT / "backend-server" / "src" / "utils" / "KLineDataFetcher.py")
        return _load_module("KLineDataFetcher", kb_path)

    def test_no_pymysql_import(self):
        """KLineDataFetcher should not import pymysql."""
        mod = self._load_kline_fetcher()
        source = inspect.getsource(mod.KLineDataFetcher)
        assert "import pymysql" not in source, "KLineDataFetcher should not import pymysql directly"

    def test_no_bare_connect_method(self):
        """KLineDataFetcher should not have connect_db/close_db methods."""
        mod = self._load_kline_fetcher()
        assert not hasattr(mod.KLineDataFetcher, "connect_db"), "KLineDataFetcher.connect_db should be removed"
        assert not hasattr(mod.KLineDataFetcher, "close_db"), "KLineDataFetcher.close_db should be removed"

    def test_no_instance_db_conn_attr(self):
        """KLineDataFetcher.__init__ should not set self.db_conn."""
        mod = self._load_kline_fetcher()
        source_lines = inspect.getsource(mod.KLineDataFetcher.__init__).splitlines()
        for line in source_lines:
            stripped = line.strip()
            assert "self.db_conn" not in stripped, f"__init__ should not set self.db_conn: {stripped}"

    def test_all_write_operations_use_dbutil(self):
        """Every SQL write in KLineDataFetcher should use DbUtil.execute_sql."""
        mod = self._load_kline_fetcher()
        source = inspect.getsource(mod.KLineDataFetcher)
        # All INSERT/UPDATE/TRUNCATE should go through DbUtil
        assert "pymysql" not in source, "KLineDataFetcher should not reference pymysql"


class TestDbUtilUsesPool:
    """Verify DbUtil.execute_sql uses DatabasePool."""

    @staticmethod
    def _load_db_util():
        util_path = str(ROOT / "backend-server" / "src" / "utils" / "DbUtil.py")
        return _load_module("DbUtil", util_path)

    def test_execute_sql_uses_get_db_cursor(self):
        mod = self._load_db_util()
        source = inspect.getsource(mod.DbUtil.execute_sql)
        assert "get_db_cursor" in source, "DbUtil.execute_sql should use get_db_cursor (connection pool)"

    def test_query_all_uses_get_db_cursor(self):
        mod = self._load_db_util()
        source = inspect.getsource(mod.DbUtil.query_all)
        assert "get_db_cursor" in source, "DbUtil.query_all should use get_db_cursor (connection pool)"


class TestNoBarePymysqlConnect:
    """Verify no service code uses bare pymysql.connect outside DatabasePool."""

    def test_only_pool_creates_connections(self):
        """The only place that should call pymysql.connect directly is DatabasePool."""
        mod = TestKLineDataFetcherDBAccess._load_kline_fetcher()
        source = inspect.getsource(mod.KLineDataFetcher)
        assert "pymysql.connect" not in source, "KLineDataFetcher should not call pymysql.connect"

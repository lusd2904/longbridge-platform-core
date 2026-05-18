from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pymysql


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ensure_refactor_env import ensure_refactor_env


def _connect_server(host: str, port: int, user: str, password: str):
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
    )


def _database_exists(connection, database: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (database,))
        return cursor.fetchone() is not None


def _table_count(connection, database: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            """,
            (database,),
        )
        row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _ensure_database(connection, database: str, charset: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET {charset} COLLATE {charset}_general_ci"
        )


def _copy_database(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    source_db: str,
    target_db: str,
) -> None:
    mysqldump = shutil.which("mysqldump")
    mysql = shutil.which("mysql")
    if not mysqldump or not mysql:
        raise RuntimeError("未找到 mysqldump 或 mysql 客户端，无法复制数据库")

    env = dict(os.environ)
    env["MYSQL_PWD"] = password

    dump_cmd = [
        mysqldump,
        f"--host={host}",
        f"--port={port}",
        f"--user={user}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        source_db,
    ]
    load_cmd = [
        mysql,
        f"--host={host}",
        f"--port={port}",
        f"--user={user}",
        target_db,
    ]

    dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, env=env)
    assert dump_proc.stdout is not None
    load_proc = subprocess.Popen(load_cmd, stdin=dump_proc.stdout, env=env)
    dump_proc.stdout.close()
    dump_code = dump_proc.wait()
    load_code = load_proc.wait()
    if dump_code != 0 or load_code != 0:
        raise RuntimeError(f"数据库复制失败: mysqldump={dump_code}, mysql={load_code}")


def main() -> None:
    env = ensure_refactor_env()

    host = env["REF_DB_HOST"]
    port = int(env["REF_DB_PORT"])
    user = env["REF_DB_USER"]
    password = env["REF_DB_PASSWORD"]
    charset = env.get("REF_DB_CHARSET") or "utf8mb4"
    source_db = env["REF_SOURCE_DB_NAME"]
    target_db = env["REF_DB_NAME"]

    connection = _connect_server(host, port, user, password)
    try:
        _ensure_database(connection, target_db, charset)
        target_tables = _table_count(connection, target_db)
        if target_tables > 0:
            print(f"目标数据库已存在数据: {target_db} ({target_tables} tables)")
            return

        if source_db == target_db:
            print(f"目标数据库与源数据库同名，跳过复制: {target_db}")
            return

        if not _database_exists(connection, source_db):
            print(f"源数据库不存在，已仅创建空库: {target_db}")
            return

        source_tables = _table_count(connection, source_db)
        if source_tables == 0:
            print(f"源数据库没有表，已仅创建空库: {target_db}")
            return
    finally:
        connection.close()

    print(f"开始复制数据库: {source_db} -> {target_db}")
    _copy_database(
        host=host,
        port=port,
        user=user,
        password=password,
        source_db=source_db,
        target_db=target_db,
    )

    verify_connection = _connect_server(host, port, user, password)
    try:
        copied_tables = _table_count(verify_connection, target_db)
    finally:
        verify_connection.close()
    print(f"数据库复制完成: {target_db} ({copied_tables} tables)")


if __name__ == "__main__":
    main()

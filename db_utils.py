#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库操作模块（只读）
"""

from typing import List
import pymysql
import pandas as pd

CHUNK_SIZE = 5000


def connect_mysql(config: dict) -> pymysql.connections.Connection:
    """创建 MySQL 只读连接"""
    conn = pymysql.connect(
        host=config["mysql_host"],
        port=config["mysql_port"],
        user=config["mysql_user"],
        password=config["mysql_password"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
        autocommit=True,
        read_timeout=30,
        write_timeout=30
    )
    return conn


def get_databases(conn) -> List[str]:
    """获取数据库列表（过滤系统库）"""
    with conn.cursor() as cursor:
        cursor.execute("SHOW DATABASES")
        return [row[0] for row in cursor.fetchall()
                if row[0] not in ("information_schema", "performance_schema", "mysql", "sys")]


def get_tables(conn, database: str) -> List[str]:
    """获取指定数据库的表列表"""
    conn.select_db(database)
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        return [row[0] for row in cursor.fetchall()]


def read_table_to_dataframe(conn, database: str, table: str) -> pd.DataFrame:
    """分批读取整个表到 DataFrame"""
    conn.select_db(database)
    query = f"SELECT * FROM `{table}`"
    chunks = []
    columns = None
    with conn.cursor() as cursor:
        cursor.execute(query)
        while True:
            rows = cursor.fetchmany(CHUNK_SIZE)
            if not rows:
                break
            if columns is None:
                columns = [desc[0] for desc in cursor.description]
            chunks.append(pd.DataFrame(rows, columns=columns))
    if not chunks:
        print("警告：表中没有数据！")
        return pd.DataFrame(columns=columns if columns else [])
    return pd.concat(chunks, ignore_index=True)
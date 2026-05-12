"""数据库初始化和连接管理。"""

from __future__ import annotations

from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from .config import MySQLConfig


CREATE_DATABASE_SQL = (
    "CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4 "
    "DEFAULT COLLATE utf8mb4_unicode_ci"
)

CREATE_MOVIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS movies (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    `rank`          INT             DEFAULT NULL,
    title           VARCHAR(255) NOT NULL,
    title_cn        VARCHAR(255) NOT NULL DEFAULT '',
    title_en        VARCHAR(255) NOT NULL DEFAULT '',
    url             VARCHAR(512) NOT NULL DEFAULT '',
    rating          DECIMAL(3,1)    DEFAULT NULL,
    comment_count   INT             DEFAULT NULL,
    summary         TEXT,
    image_url       VARCHAR(512) NOT NULL DEFAULT '',
    source_page     VARCHAR(512) NOT NULL DEFAULT '',
    image_file      VARCHAR(512) NOT NULL DEFAULT '',
    director        VARCHAR(255) NOT NULL DEFAULT '',
    screenwriter    VARCHAR(255) NOT NULL DEFAULT '',
    actors          TEXT,
    genres          VARCHAR(255) NOT NULL DEFAULT '',
    country         VARCHAR(255) NOT NULL DEFAULT '',
    language        VARCHAR(255) NOT NULL DEFAULT '',
    release_date    VARCHAR(255) NOT NULL DEFAULT '',
    runtime         INT             DEFAULT NULL,
    imdb            VARCHAR(50)  NOT NULL DEFAULT '',
    detail_error    TEXT,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_url (url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_COMMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    movie_id     INT           NOT NULL,
    `user`       VARCHAR(255)  NOT NULL DEFAULT '',
    rating       VARCHAR(50)   NOT NULL DEFAULT '',
    comment_time VARCHAR(100)  NOT NULL DEFAULT '',
    helpful      INT             DEFAULT NULL,
    `comment`      TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
    INDEX idx_movie_id (movie_id),
    UNIQUE KEY uk_movie_user_time (movie_id, `user`, comment_time, `comment`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def get_connection(cfg: MySQLConfig) -> Any:
    """返回一个指向已配置数据库的 pymysql 连接。"""
    return pymysql.connect(**cfg.connect_kwargs)  # type: ignore[arg-type]


def get_dict_connection(cfg: MySQLConfig) -> Any:
    """返回一个以字典形式返回查询结果的 pymysql 连接。"""
    return pymysql.connect(
        cursorclass=DictCursor, **cfg.connect_kwargs  # type: ignore[arg-type]
    )


def init_database(cfg: MySQLConfig) -> None:
    """如果数据库不存在则创建（不指定数据库名进行连接）。"""
    kwargs = {k: v for k, v in cfg.connect_kwargs.items() if k != "database"}
    conn = pymysql.connect(**kwargs)  # type: ignore[arg-type]
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_DATABASE_SQL.format(db=cfg.database))
        conn.commit()
    finally:
        conn.close()


def drop_tables(cfg: MySQLConfig) -> None:
    """删除 comments 表和 movies 表（遵从外键约束，先删子表）。"""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS comments")
            cur.execute("DROP TABLE IF EXISTS movies")
        conn.commit()
    finally:
        conn.close()


MIGRATE_MOVIES_SQL = [
    "ALTER TABLE movies MODIFY COLUMN `rank` INT DEFAULT NULL",
    "ALTER TABLE movies MODIFY COLUMN `rating` DECIMAL(3,1) DEFAULT NULL",
    "ALTER TABLE movies MODIFY COLUMN `comment_count` INT DEFAULT NULL",
]
"""用于将现有数据库列迁移为数字类型的 ALTER TABLE 语句。"""

MIGRATE_COMMENTS_SQL = [
    "ALTER TABLE comments MODIFY COLUMN `helpful` INT DEFAULT NULL",
]


def migrate_schema(cfg: MySQLConfig) -> None:
    """将现有表的 VARCHAR 列迁移为数字类型。

    对已迁移的表调用也是安全的；当列已经是目标类型时，
    每个 ALTER TABLE 语句不产生实际效果。
    """
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            for sql in MIGRATE_MOVIES_SQL + MIGRATE_COMMENTS_SQL:
                try:
                    cur.execute(sql)
                except Exception:
                    pass  # 列可能已经是目标类型，无需迁移
        conn.commit()
    finally:
        conn.close()


def create_tables(cfg: MySQLConfig) -> None:
    """如果 movies 表和 comments 表尚不存在则创建。"""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_MOVIES_TABLE_SQL)
            cur.execute(CREATE_COMMENTS_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()
    migrate_schema(cfg)

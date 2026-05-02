"""Database initialisation and connection management."""

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
    title           VARCHAR(255) NOT NULL,
    url             VARCHAR(512) NOT NULL DEFAULT '',
    rating          VARCHAR(10)  NOT NULL DEFAULT '',
    comment_count   VARCHAR(20)  NOT NULL DEFAULT '',
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
    runtime         VARCHAR(100) NOT NULL DEFAULT '',
    imdb            VARCHAR(50)  NOT NULL DEFAULT '',
    detail_error    TEXT,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_url (url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_COMMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    movie_id     INT       NOT NULL,
    raw_comment  TEXT      NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
    INDEX idx_movie_id (movie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def get_connection(cfg: MySQLConfig) -> Any:
    """Return a pymysql connection to the configured database."""
    return pymysql.connect(**cfg.connect_kwargs)  # type: ignore[arg-type]


def get_dict_connection(cfg: MySQLConfig) -> Any:
    """Return a pymysql connection that yields rows as dicts."""
    return pymysql.connect(
        cursorclass=DictCursor, **cfg.connect_kwargs  # type: ignore[arg-type]
    )


def init_database(cfg: MySQLConfig) -> None:
    """Create the database if it does not exist (connect without db name)."""
    kwargs = {k: v for k, v in cfg.connect_kwargs.items() if k != "database"}
    conn = pymysql.connect(**kwargs)  # type: ignore[arg-type]
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_DATABASE_SQL.format(db=cfg.database))
        conn.commit()
    finally:
        conn.close()


def create_tables(cfg: MySQLConfig) -> None:
    """Create movies & comments tables if they do not already exist."""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_MOVIES_TABLE_SQL)
            cur.execute(CREATE_COMMENTS_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()

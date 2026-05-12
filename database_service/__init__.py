"""数据库服务包 —— MySQL 存储与备份导出。"""
from __future__ import annotations

from .config import MySQLConfig
from .repository import save_movies_with_comments
from .exporter import export_backup

__all__ = [
    "MySQLConfig",
    "save_to_mysql",
    "export_backup",
]


def save_to_mysql(
    items: list[dict],
    *,
    recreate: bool = False,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "123456",
    database: str = "douban",
    backup_dir: str = "data/database/backup",
) -> int:
    """
    统一入口：将数据存入 MySQL，并导出 JSON / CSV 备份。

    Parameters
    ----------
    items : list[dict]
        由 ``DoubanItem.to_dict()`` 生成的电影字典列表。
    recreate : bool
        如果为 True，入库前先删除并重建表（用于全量导入）。
    host, port, user, password, database :
        MySQL 连接参数。
    backup_dir :
        备份文件输出目录。

    Returns
    -------
    实际写入 MySQL 的电影数量。
    """
    cfg = MySQLConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        backup_dir=backup_dir,
    )
    inserted = save_movies_with_comments(cfg, items, recreate=recreate)
    export_backup(cfg)
    return inserted

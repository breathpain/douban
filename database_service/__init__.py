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
    Unified entry: save items to MySQL, then export JSON / CSV backups.

    Parameters
    ----------
    items : list[dict]
        Movie dicts as produced by ``DoubanItem.to_dict()``.
    recreate : bool
        If True, drop & recreate tables before inserting (used for full import).
    host, port, user, password, database :
        MySQL connection parameters.
    backup_dir :
        Where to write backup files.

    Returns
    -------
    Number of movies inserted into MySQL.
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

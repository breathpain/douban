"""数据库服务 MySQL 连接配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MySQLConfig:
    """数据库连接设置。"""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "123456"
    database: str = "douban"
    charset: str = "utf8mb4"

    backup_dir: str = "data/database/backup"
    """从 MySQL 导出的 JSON / CSV 备份文件的输出目录。"""

    @property
    def dsn(self) -> str:
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )

    @property
    def connect_kwargs(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
        }

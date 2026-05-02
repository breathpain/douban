"""MySQL connection configuration for member B."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MySQLConfig:
    """Database connection settings."""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "douban"
    charset: str = "utf8mb4"

    backup_dir: str = "data/member_b/backup"
    """Output directory for JSON / CSV backup files exported from MySQL."""

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

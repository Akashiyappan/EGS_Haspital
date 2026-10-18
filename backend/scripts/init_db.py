"""Ensure the database exists before running Alembic migrations.

Idempotent: Connects to MySQL server and creates the target database if it doesn't already exist.
"""

import sys

from sqlalchemy.engine import make_url

from app.core.config import settings


def ensure_database() -> None:
    url = make_url(settings.DATABASE_URL)

    # SQLite creates the file automatically upon connection
    if "sqlite" in url.drivername:
        print(f"[init_db] SQLite configured ({url.database}). Ready.")
        return

    # MySQL database creation
    if "mysql" in url.drivername:
        try:
            import pymysql
        except ImportError:
            print("[init_db] pymysql is not installed; skipping automatic DB creation.")
            return

        db_name = url.database
        if not db_name:
            print("[init_db] No database name found in DATABASE_URL.")
            return

        host = url.host or "127.0.0.1"
        port = url.port or 3306
        user = url.username or "root"
        password = url.password or ""

        print(f"[init_db] Checking MySQL database '{db_name}' on {host}:{port} (user: {user})...")
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                    )
                conn.commit()
                print(f"[init_db] Database '{db_name}' is verified and ready.")
            finally:
                conn.close()
        except Exception as exc:
            print(f"[init_db] Failed to ensure database '{db_name}': {exc}")
            print("Please run this command manually in your MySQL shell:")
            print(f"    CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4;")
            sys.exit(1)


if __name__ == "__main__":
    ensure_database()

import os
import psycopg2
from dotenv import load_dotenv


def get_conn():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    # Fallback to discrete vars
    host = os.getenv("DB_HOST", "localhost")
    name = os.getenv("DB_NAME", "your_db_name")
    user = os.getenv("DB_USER", "your_user")
    password = os.getenv("DB_PASSWORD", "your_password")
    port = os.getenv("DB_PORT", "5432")
    return psycopg2.connect(host=host, dbname=name, user=user, password=password, port=port)


def main():
    conn = get_conn()
    cur = conn.cursor()

    # Create table if not exists
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS group_slots (
          group_id     INTEGER PRIMARY KEY,
          prolific_pid TEXT UNIQUE,
          claimed_at   TIMESTAMPTZ
        );
        """
    )

    # Seed 1..200 using generate_series, idempotent
    cur.execute(
        """
        INSERT INTO group_slots(group_id)
        SELECT gs FROM generate_series(1,200) AS gs
        ON CONFLICT(group_id) DO NOTHING;
        """
    )

    # Report
    cur.execute("SELECT COUNT(*) FROM group_slots")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM group_slots WHERE prolific_pid IS NULL")
    free = cur.fetchone()[0]
    conn.commit()

    print(f"Seed complete. Total slots: {total}, free: {free}")


if __name__ == "__main__":
    main()



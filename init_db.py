import mysql.connector
from config import Config

def init_db():
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DATABASE
    )
    try:
        with conn.cursor() as cur:
            with open('schema.sql', 'r') as f:
                # Split SQL statements (MySQL requires single statements)
                for statement in f.read().split(';'):
                    if statement.strip():
                        cur.execute(statement)
            conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
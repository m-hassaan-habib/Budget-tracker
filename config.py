import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    MYSQL_HOST = os.getenv('MYSQL_HOST')
    MYSQL_USER = os.getenv('MYSQL_USER')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'budget_db')

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    AVATAR_FOLDER = os.path.join(UPLOAD_FOLDER, 'avatars')
    RECEIPT_FOLDER = os.path.join(UPLOAD_FOLDER, 'receipts')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_ATTACH_EXT = {"pdf", "png", "jpg", "jpeg", "doc"}

    @staticmethod
    def init_db(app):
        try:
            app.db_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="budget_pool",
                pool_size=5,
                host=Config.MYSQL_HOST,
                user=Config.MYSQL_USER,
                password=Config.MYSQL_PASSWORD,
                database=Config.MYSQL_DATABASE
            )
        except mysql.connector.Error as e:
            import logging
            logging.error(f"Could not initialize database pool: {e}")
            app.db_pool = None

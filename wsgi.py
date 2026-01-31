from FlaskApi import app
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv()


if __name__ == "__main__":
    app.run()
from flask import Flask
from threading import Thread
import logging

# Отключаем лишний шум от Flask в логах
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask('')

@app.route('/')
def home():
    return "I am alive and trading!"

def run():
    # Render.com ищет порт 10000 или берет из окружения
    # Но для внутреннего теста ставим 8080
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

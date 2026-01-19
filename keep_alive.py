from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I am alive and trading!"

def run():
    # Запускаем на порту 8080 или том, который даст Render
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

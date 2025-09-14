from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "EALPA Bot is alive and running!"

def run():
  # Render የ PORT ተለዋዋጭን በራሱ ጊዜ ይሰጣል
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

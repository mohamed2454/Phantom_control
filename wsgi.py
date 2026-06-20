import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Phantom Bot is running!"

if __name__ == '__main__':
    port = int(os.getenv('PORT', 7860))
    app.run(host='0.0.0.0', port=port, debug=False)
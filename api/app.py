import os
import time
from datetime import datetime

from flask import Flask


app = Flask(__name__)


@app.route("/api/date")
def date():
    now = datetime.now()
    return (
        '{"date": "' + now.isoformat() + '"}',
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/error")
def error():
    raise ValueError("this is an example error")


@app.route("/api/not-auth")
def not_auth():
    return (
        "Not Authorized",
        401,
        {"Content-Type": "application/json"},
    )


@app.route("/api/timeout")
def timeout():
    time.sleep(60)


# For running in a local Python environment, which be started by running:
# PORT=8000 python app.py
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8000))
    app.run(
        host="0.0.0.0", port=PORT,
    )

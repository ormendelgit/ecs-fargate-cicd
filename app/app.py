from flask import Flask, jsonify
import socket
import os

app = Flask(__name__)

@app.route("/")
def health_check():
    return jsonify({
        "status": "healthy",
        "container_id": socket.gethostname(),
        "environment": os.getenv("APP_ENV", "production"),
        "version": "1.0.0"
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)

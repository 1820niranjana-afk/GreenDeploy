
from flask import Flask, render_template, jsonify
import psutil

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/module1")
def module1():
    return render_template("module1.html")

@app.route("/api/metrics")
def metrics():
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()

    return jsonify({
        "cpu": cpu,
        "ram": memory.percent,
        "ram_used": round(memory.used / (1024 ** 3), 2),
        "ram_total": round(memory.total / (1024 ** 3), 2)
    })

if __name__ == "__main__":
    app.run(debug=True)

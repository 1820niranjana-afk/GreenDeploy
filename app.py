
from flask import Flask, render_template, jsonify, request
import psutil
import docker
import json
import os
import threading
import requests
from datetime import datetime

from modules.cicd import (
    trigger_pipeline,
    get_pipeline_status
)

# ==================================================
# 1. INITIALIZE APPLICATION
# ==================================================

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "greendeploy_secret_key"
)

CONTAINER_NAME = "greendeploy-container"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(
    BASE_DIR,
    "optimization_history.json"
)

history_lock = threading.RLock()


# ==================================================
# 2. DOCKER CONNECTION
# ==================================================

try:
    docker_client = docker.from_env(timeout=10)
    docker_client.ping()

    DOCKER_AVAILABLE = True
    print("Docker connected successfully")

except Exception as error:
    print("Docker connection error:", error)

    docker_client = None
    DOCKER_AVAILABLE = False


def get_container():
    if not DOCKER_AVAILABLE:
        raise RuntimeError("Docker is not available")

    return docker_client.containers.get(CONTAINER_NAME)


# ==================================================
# 3. RESOURCE ALLOCATION HELPERS
# ==================================================

def get_cpu_allocation(container):
    config = container.attrs["HostConfig"]

    nano_cpus = config.get("NanoCpus", 0)

    if nano_cpus:
        return round(nano_cpus / 1_000_000_000, 2)

    quota = config.get("CpuQuota", 0)
    period = config.get("CpuPeriod", 0)

    if quota > 0 and period > 0:
        return round(quota / period, 2)

    return None


def get_memory_allocation(container):
    memory = container.attrs["HostConfig"].get("Memory", 0)

    if memory > 0:
        return round(memory / (1024 ** 2), 2)

    return None


# ==================================================
# 4. OPTIMIZATION HISTORY
# ==================================================

def get_optimization_history():
    with history_lock:

        if not os.path.exists(HISTORY_FILE):
            return []

        try:
            with open(HISTORY_FILE, "r") as file:
                history = json.load(file)

            if not isinstance(history, list):
                return []

            for record in history:
                record.setdefault("previous_cpu", "N/A")
                record.setdefault(
                    "new_cpu",
                    record.get("cpu_cores", "N/A")
                )
                record.setdefault("previous_ram", "N/A")
                record.setdefault(
                    "new_ram",
                    record.get("memory_mb", "N/A")
                )

            return history

        except (json.JSONDecodeError, OSError):
            app.logger.exception("History reading failed")
            return []


def save_optimization_history(record):
    with history_lock:

        history = get_optimization_history()
        history.insert(0, record)

        temp_file = HISTORY_FILE + ".tmp"

        with open(temp_file, "w") as file:
            json.dump(history[:50], file, indent=4)

        os.replace(temp_file, HISTORY_FILE)


# ==================================================
# 5. PAGE ROUTES
# ==================================================

@app.route("/")
@app.route("/dashboard")
def home():
    return render_template("dashboard.html")


@app.route("/module1")
def module1():
    return render_template("module1.html")


@app.route("/module2")
def module2():
    return render_template("module2.html")


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    return render_template("register.html")


# ==================================================
# 6. MODULE 1 - TRIGGER CI/CD PIPELINE
# ==================================================

@app.route("/api/run-pipeline", methods=["POST"])
def run_pipeline():
    try:
        data = request.get_json(silent=True) or {}

        repo_url = data.get("repo_url", "").strip()
        branch = data.get("branch", "main").strip()

        if not repo_url:
            return jsonify({
                "success": False,
                "error": "GitHub repository URL is required"
            }), 400

        if not branch:
            return jsonify({
                "success": False,
                "error": "Branch name is required"
            }), 400

        result = trigger_pipeline(
            repo_url,
            branch,
            GITHUB_TOKEN
        )

        return jsonify(result), 200

    except ValueError as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except requests.RequestException as error:
        app.logger.exception("GitHub connection failed")

        return jsonify({
            "success": False,
            "error": "Unable to connect to GitHub: " + str(error)
        }), 502

    except Exception as error:
        app.logger.exception("Pipeline trigger failed")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==================================================
# 7. MODULE 1 - CHECK PIPELINE STATUS
# ==================================================

@app.route("/api/pipeline-status", methods=["GET"])
def pipeline_status():
    try:
        repo_url = request.args.get("repo_url", "").strip()
        branch = request.args.get("branch", "main").strip()

        if not repo_url:
            return jsonify({
                "success": False,
                "error": "Repository URL is required"
            }), 400

        result = get_pipeline_status(
            repo_url,
            branch,
            GITHUB_TOKEN
        )

        return jsonify(result), 200

    except ValueError as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except requests.RequestException as error:
        app.logger.exception("GitHub status connection failed")

        return jsonify({
            "success": False,
            "error": "GitHub connection failed: " + str(error)
        }), 502

    except Exception as error:
        app.logger.exception("Pipeline status failed")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==================================================
# 8. MODULE 2 - SYSTEM MONITORING
# ==================================================

@app.route("/api/metrics")
def metrics():
    cpu = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()

    return jsonify({
        "cpu": cpu,
        "ram": memory.percent,
        "ram_used": round(memory.used / (1024 ** 3), 2),
        "ram_total": round(memory.total / (1024 ** 3), 2)
    })


# ==================================================
# 9. MODULE 2 - DOCKER MONITORING
# ==================================================

@app.route("/api/docker-metrics")
def docker_metrics():
    try:
        container = get_container()
        container.reload()

        if container.status != "running":
            return jsonify({
                "error": "Container is not running"
            }), 503

        stats = container.stats(stream=False)

        cpu_stats = stats.get("cpu_stats", {})
        previous_stats = stats.get("precpu_stats", {})

        cpu_usage = cpu_stats.get(
            "cpu_usage", {}
        ).get("total_usage", 0)

        previous_usage = previous_stats.get(
            "cpu_usage", {}
        ).get("total_usage", 0)

        cpu_delta = cpu_usage - previous_usage

        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - previous_stats.get("system_cpu_usage", 0)
        )

        online_cpus = cpu_stats.get("online_cpus", 1) or 1

        cpu_percent = 0

        if system_delta > 0 and cpu_delta >= 0:
            cpu_percent = (
                cpu_delta / system_delta
            ) * online_cpus * 100

        memory_stats = stats.get("memory_stats", {})

        memory_used = memory_stats.get("usage", 0)
        memory_limit = memory_stats.get("limit", 0)

        # Exclude Linux cache where available.
        memory_details = memory_stats.get("stats", {})

        cache = memory_details.get(
            "inactive_file",
            memory_details.get("cache", 0)
        )

        actual_memory = max(memory_used - cache, 0)

        ram_percent = (
            actual_memory / memory_limit * 100
            if memory_limit > 0 else 0
        )

        return jsonify({
            "status": "Active",
            "cpu": round(cpu_percent, 2),
            "ram": round(ram_percent, 2),
            "memory_used_mb": round(
                actual_memory / (1024 ** 2), 2
            ),
            "memory_limit_mb": round(
                memory_limit / (1024 ** 2), 2
            )
        })

    except Exception as error:
        app.logger.exception("Docker monitoring failed")

        return jsonify({
            "error": str(error)
        }), 500


# ==================================================
# 10. MODULE 2 - CONTAINER CONFIGURATION
# ==================================================

@app.route("/api/container-config")
def container_config():
    try:
        container = get_container()
        container.reload()

        return jsonify({
            "cpu_cores": get_cpu_allocation(container),
            "memory_mb": get_memory_allocation(container),
            "status": container.status
        })

    except Exception as error:
        app.logger.exception("Container configuration failed")

        return jsonify({
            "error": str(error)
        }), 500


# ==================================================
# 11. MODULE 2 - RESOURCE OPTIMIZATION
# ==================================================

@app.route("/api/optimize-container", methods=["POST"])
def optimize_container():
    try:
        data = request.get_json(silent=True) or {}

        cpu_cores = float(data.get("cpu_cores", 1))
        memory_mb = int(data.get("memory_mb", 512))

        if cpu_cores not in [0.5, 1.0, 2.0]:
            return jsonify({
                "success": False,
                "error": "Invalid CPU allocation"
            }), 400

        if memory_mb not in [256, 512, 1024]:
            return jsonify({
                "success": False,
                "error": "Invalid RAM allocation"
            }), 400

        container = get_container()
        container.reload()

        if container.status != "running":
            return jsonify({
                "success": False,
                "error": "Container is not running"
            }), 400

        previous_cpu = get_cpu_allocation(container)
        previous_ram = get_memory_allocation(container)

        result = container.update(
            cpu_period=100000,
            cpu_quota=int(cpu_cores * 100000),
            mem_limit=memory_mb * 1024 * 1024,
            memswap_limit=memory_mb * 1024 * 1024
        )

        warnings = result.get("Warnings") or []

        if warnings:
            return jsonify({
                "success": False,
                "error": str(warnings)
            }), 500

        record = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "previous_cpu": previous_cpu if previous_cpu is not None else "N/A",
            "new_cpu": cpu_cores,
            "previous_ram": previous_ram if previous_ram is not None else "N/A",
            "new_ram": memory_mb,
            "status": "Success"
        }

        save_optimization_history(record)

        return jsonify({
            "success": True,
            "message": "Container resources optimized successfully",
            "previous_cpu": previous_cpu,
            "new_cpu": cpu_cores,
            "previous_ram": previous_ram,
            "new_ram": memory_mb
        })

    except Exception as error:
        app.logger.exception("Resource optimization failed")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==================================================
# 12. MODULE 2 - OPTIMIZATION HISTORY
# ==================================================

@app.route("/api/optimization-history")
def optimization_history():
    return jsonify({
        "history": get_optimization_history()
    })


# ==================================================
# 13. MODULE 2 - DOCKER STATUS
# ==================================================

@app.route("/api/docker-status")
def docker_status():
    try:
        container = get_container()
        container.reload()

        return jsonify({
            "docker_available": True,
            "container_status": container.status,
            "container_name": CONTAINER_NAME
        })

    except Exception as error:
        return jsonify({
            "docker_available": DOCKER_AVAILABLE,
            "container_status": "Unavailable",
            "error": str(error)
        }), 503


# ==================================================
# 14. HEALTH CHECK
# ==================================================

@app.route("/api/health")
def health():
    return jsonify({
        "application": "GreenDeploy",
        "status": "Running",
        "docker_available": DOCKER_AVAILABLE,
        "github_token_configured": bool(GITHUB_TOKEN)
    })


# ==================================================
# 15. RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )


from flask import Flask, render_template, jsonify, request
import psutil
import docker

app = Flask(__name__)

# Connect to Docker
docker_client = docker.from_env()


@app.route("/")
def home():
    return render_template("dashboard.html")


@app.route("/module1")
def module1():
    return render_template("module1.html")


@app.route("/module2")
def module2():
    return render_template("module2.html")


# System monitoring API
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


# Docker container monitoring API
@app.route("/api/docker-metrics")
def docker_metrics():

    try:
        container = docker_client.containers.get(
            "greendeploy-container"
        )

        stats = container.stats(stream=False)

        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )

        system_delta = (
            stats["cpu_stats"]["system_cpu_usage"]
            - stats["precpu_stats"]["system_cpu_usage"]
        )

        online_cpus = stats["cpu_stats"].get(
            "online_cpus",
            len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
        )

        cpu_percent = 0

        if system_delta > 0 and cpu_delta >= 0:
            cpu_percent = (
                cpu_delta / system_delta
            ) * online_cpus * 100

        memory_used = stats["memory_stats"]["usage"]
        memory_limit = stats["memory_stats"]["limit"]

        ram_percent = (
            memory_used / memory_limit * 100
            if memory_limit > 0 else 0
        )

        return jsonify({
            "cpu": round(cpu_percent, 2),
            "ram": round(ram_percent, 2),
            "memory_used_mb": round(memory_used / (1024 ** 2), 2),
            "memory_limit_mb": round(memory_limit / (1024 ** 2), 2)
        })

    except docker.errors.NotFound:
        return jsonify({
            "error": "GreenDeploy container not found"
        }), 404

    except Exception as error:
        return jsonify({
            "error": str(error)
        }), 500


# Docker resource optimization API
@app.route("/api/optimize-container", methods=["POST"])
def optimize_container():

    try:
        data = request.get_json()

        cpu_cores = float(data.get("cpu_cores", 1))
        memory_mb = int(data.get("memory_mb", 512))

        # Allow only predefined resource limits
        if cpu_cores not in [0.5, 1.0, 2.0]:
            return jsonify({
                "error": "Invalid CPU allocation"
            }), 400

        if memory_mb not in [256, 512, 1024]:
            return jsonify({
                "error": "Invalid memory allocation"
            }), 400

        # Get running GreenDeploy container
        container = docker_client.containers.get(
            "greendeploy-container"
        )

        # Apply CPU and RAM limits
        container.update(
            cpu_period=100000,
            cpu_quota=int(cpu_cores * 100000),
            mem_limit=f"{memory_mb}m"
        )

        return jsonify({
            "success": True,
            "message": "Docker resource limits updated successfully",
            "cpu_cores": cpu_cores,
            "memory_mb": memory_mb
        })

    except docker.errors.NotFound:
        return jsonify({
            "error": "GreenDeploy container not found"
        }), 404

    except Exception as error:
        return jsonify({
            "error": str(error)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )

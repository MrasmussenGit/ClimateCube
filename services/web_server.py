import os
import socket

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for
)

try:
    from .database import (
        DB_FILE,
        HISTORY_RANGES,
        get_latest_readings,
        get_hidden_sensor_count,
        get_sensor,
        get_sensors,
        get_temperature_history,
        update_sensor_name,
        update_sensor_visibility
    )
except ImportError:
    from database import (
        DB_FILE,
        HISTORY_RANGES,
        get_latest_readings,
        get_hidden_sensor_count,
        get_sensor,
        get_sensors,
        get_temperature_history,
        update_sensor_name,
        update_sensor_visibility
    )


app = Flask(__name__)


def get_storage_warning_percent():
    try:
        threshold = float(os.environ.get(
            "CLIMATECUBE_STORAGE_WARNING_PERCENT",
            "10"
        ))
    except ValueError:
        threshold = 10.0

    return min(100.0, max(0.0, threshold))


def format_bytes(byte_count):
    value = float(byte_count)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{value:.{precision}f} {unit}"
        value /= 1024


def get_storage_info():
    database_path = DB_FILE.resolve()
    filesystem = os.statvfs(database_path.parent)
    total_bytes = filesystem.f_blocks * filesystem.f_frsize
    available_bytes = filesystem.f_bavail * filesystem.f_frsize
    available_percent = (
        available_bytes / total_bytes * 100 if total_bytes else 0
    )
    warning_percent = get_storage_warning_percent()
    database_bytes = database_path.stat().st_size if database_path.exists() else 0

    return {
        "database_bytes": database_bytes,
        "database_size": format_bytes(database_bytes),
        "total_bytes": total_bytes,
        "total_size": format_bytes(total_bytes),
        "available_bytes": available_bytes,
        "available_size": format_bytes(available_bytes),
        "available_percent": round(available_percent, 1),
        "warning_percent": warning_percent,
        "is_low": available_percent < warning_percent
    }


def get_server_info():
    hostname = socket.gethostname().split(".")[0]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("10.255.255.255", 1))
        ip_address = sock.getsockname()[0]
    except OSError:
        ip_address = "Unknown"
    finally:
        sock.close()

    return {
        "hostname": hostname,
        "ip_address": ip_address
    }


@app.route("/")
def dashboard():
    show_hidden = request.args.get("show_hidden") == "1"

    return render_template(
        "dashboard.html",
        readings=get_latest_readings(include_inactive=show_hidden),
        hidden_sensor_count=get_hidden_sensor_count(),
        show_hidden=show_hidden,
        server_info=get_server_info(),
        storage_info=get_storage_info()
    )


@app.route("/api/latest")
def latest_api():
    show_hidden = request.args.get("show_hidden") == "1"
    return jsonify(get_latest_readings(include_inactive=show_hidden))


@app.route("/api/storage")
def storage_api():
    return jsonify(get_storage_info())


@app.route("/settings")
def settings():
    return render_template(
        "settings.html",
        sensors=get_sensors(),
        saved=request.args.get("saved") == "1",
        visibility_saved=request.args.get("visibility_saved") == "1",
        error=request.args.get("error")
    )


@app.route("/settings/sensor/<int:sensor_id>/name", methods=["POST"])
def save_sensor_name(sensor_id):
    sensor_name = request.form.get("sensor_name", "").strip()

    if not sensor_name:
        return redirect(url_for(
            "settings",
            error="Sensor name cannot be empty."
        ))

    if len(sensor_name) > 50:
        return redirect(url_for(
            "settings",
            error="Sensor name must be 50 characters or fewer."
        ))

    if not update_sensor_name(sensor_id, sensor_name):
        abort(404)

    return redirect(url_for("settings", saved="1"))


@app.route("/settings/sensor/<int:sensor_id>/visibility", methods=["POST"])
def save_sensor_visibility(sensor_id):
    is_visible = request.form.get("is_visible") == "1"

    if not update_sensor_visibility(sensor_id, is_visible):
        abort(404)

    return redirect(url_for("settings", visibility_saved="1"))


@app.route("/history/<int:sensor_id>")
def history(sensor_id):
    sensor = get_sensor(sensor_id)

    if sensor is None:
        abort(404)

    return render_template(
        "history.html",
        sensor=sensor
    )


@app.route("/api/history/<int:sensor_id>")
def history_api(sensor_id):
    sensor = get_sensor(sensor_id)

    if sensor is None:
        abort(404)

    range_name = request.args.get("range", "24h")

    if range_name not in HISTORY_RANGES:
        return jsonify({
            "error": "Invalid range",
            "valid_ranges": list(HISTORY_RANGES)
        }), 400

    return jsonify({
        "sensor": sensor,
        "range": range_name,
        "readings": get_temperature_history(sensor_id, range_name)
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )

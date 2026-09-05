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
        HISTORY_RANGES,
        get_latest_readings,
        get_sensor,
        get_sensors,
        get_temperature_history,
        update_sensor_name
    )
except ImportError:
    from database import (
        HISTORY_RANGES,
        get_latest_readings,
        get_sensor,
        get_sensors,
        get_temperature_history,
        update_sensor_name
    )


app = Flask(__name__)


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
    return render_template(
        "dashboard.html",
        readings=get_latest_readings(),
        server_info=get_server_info()
    )


@app.route("/api/latest")
def latest_api():
    return jsonify(get_latest_readings())


@app.route("/settings")
def settings():
    return render_template(
        "settings.html",
        sensors=get_sensors(),
        saved=request.args.get("saved") == "1",
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

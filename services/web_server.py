import sqlite3
from pathlib import Path
import socket

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    url_for
)

app = Flask(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"

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


def get_latest_readings():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            s.sensor_id,
            s.sensor_name,
            s.device_id,
            s.ip_address,
            r.pico_ts AS reading_time,
            r.temperature_c,
            r.humidity_pct,
            r.pressure_hpa
        FROM sensor_reading AS r
        JOIN sensor AS s
            ON s.sensor_id = r.sensor_id
        WHERE r.reading_id IN
        (
            SELECT MAX(reading_id)
            FROM sensor_reading
            GROUP BY sensor_id
        )
        ORDER BY s.sensor_name
        """
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


HISTORY_RANGES = {
    "6h": ("-6 hours", 60),
    "24h": ("-24 hours", 300),
    "3d": ("-3 days", 900),
    "7d": ("-7 days", 1800)
}


def get_sensor(sensor_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT sensor_id, sensor_name, device_id, ip_address
        FROM sensor
        WHERE sensor_id = ?
        """,
        (sensor_id,)
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def get_sensors():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            s.sensor_id,
            s.sensor_name,
            s.device_id,
            s.ip_address,
            MAX(COALESCE(r.pico_ts, r.insert_ts)) AS last_reading_time
        FROM sensor AS s
        LEFT JOIN sensor_reading AS r
            ON r.sensor_id = s.sensor_id
        GROUP BY
            s.sensor_id,
            s.sensor_name,
            s.device_id,
            s.ip_address
        ORDER BY s.sensor_name
        """
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def update_sensor_name(sensor_id, sensor_name):
    conn = sqlite3.connect(DB_FILE)

    cursor = conn.execute(
        """
        UPDATE sensor
        SET sensor_name = ?
        WHERE sensor_id = ?
        """,
        (sensor_name, sensor_id)
    )

    conn.commit()
    updated = cursor.rowcount == 1
    conn.close()

    return updated


def get_temperature_history(sensor_id, range_name):
    modifier, bucket_seconds = HISTORY_RANGES[range_name]

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        WITH latest AS
        (
            SELECT MAX(COALESCE(pico_ts, insert_ts)) AS latest_ts
            FROM sensor_reading
            WHERE sensor_id = ?
        )
        SELECT
            MAX(COALESCE(r.pico_ts, r.insert_ts)) AS reading_time,
            AVG(r.temperature_c) AS temperature_c
        FROM sensor_reading AS r
        CROSS JOIN latest
        WHERE r.sensor_id = ?
          AND datetime(
                replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
              ) >= datetime(
                replace(latest.latest_ts, 'T', ' '), ?
              )
        GROUP BY
            CAST(
                strftime(
                    '%s',
                    replace(COALESCE(r.pico_ts, r.insert_ts), 'T', ' ')
                ) AS INTEGER
            ) / ?
        ORDER BY reading_time
        """,
        (sensor_id, sensor_id, modifier, bucket_seconds)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >
    <meta http-equiv="refresh" content="10">

    <title>ClimateCube</title>

    <style>

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
        }

        .server-info {
            margin-top: 30px;
            color: #667788;
            font-size: 13px;
            text-align: center;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .unit-button,
        .settings-link {
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            background: #243447;
            color: white;
            font-size: 16px;
            cursor: pointer;
            text-decoration: none;
        }

        .unit-button:hover,
        .settings-link:hover {
            background: #3a5068;
        }
        body {
            margin: 0;
            padding: 30px;
            background: #eef2f6;
            color: #243447;
            font-family: Arial, sans-serif;
        }

        h1 {
            margin-bottom: 5px;
        }

        .subtitle {
            margin-top: 0;
            color: #667788;
        }

        .sensors {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }

        .sensor {
            padding: 22px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
        }

        .sensor h2 {
            margin-top: 0;
        }

        .temperature {
            margin: 20px 0;
            color: #d35400;
            font-size: 42px;
            font-weight: bold;
        }

        .reading {
            display: flex;
            justify-content: space-between;
            padding: 9px 0;
            border-bottom: 1px solid #e5e9ed;
        }

        .label {
            color: #667788;
        }

        .timestamp {
            margin-top: 18px;
            color: #778899;
            font-size: 13px;
        }

        .history-link {
            display: inline-block;
            margin-top: 18px;
            color: #243447;
            font-weight: bold;
            text-decoration: none;
        }

        .history-link:hover {
            text-decoration: underline;
        }

        .empty {
            padding: 20px;
            background: white;
            border-radius: 12px;
        }
    </style>
</head>

<body>
    <div class="header">
        <div>
            <h1>ClimateCube</h1>

            <p class="subtitle">
                Latest sensor readings — refreshes every 10 seconds
            </p>
        </div>

        <div class="header-actions">
            <a class="settings-link" href="/settings">Settings</a>

            <button
                id="unit-button"
                class="unit-button"
                type="button"
            >
                Show °F
            </button>
        </div>
    </div>

    {% if readings %}
        <div class="sensors">
            {% for reading in readings %}
                <section class="sensor">
                    <h2>{{ reading.sensor_name }}</h2>

                    <div
                        class="temperature"
                        data-temperature-c="{{ reading.temperature_c }}"
                    >
                        {{ "%.2f"|format(reading.temperature_c) }} °C
                    </div>

                    <div class="reading">
                        <span class="label">Humidity</span>

                        <span>
                            {{ "%.2f"|format(reading.humidity_pct) }} %
                        </span>
                    </div>

                    <div class="reading">
                        <span class="label">Pressure</span>

                        <span>
                            {{ "%.2f"|format(reading.pressure_hpa) }} hPa
                        </span>
                    </div>

                    <div class="reading">
                        <span class="label">Device</span>
                        <span>{{ reading.device_id }}</span>
                    </div>

                    <div class="reading">
                        <span class="label">IP address</span>
                        <span>{{ reading.ip_address or "Unknown" }}</span>
                    </div>

                    <div class="timestamp">
                        Reading time: {{ reading.reading_time }}
                    </div>

                    <a
                        class="history-link"
                        href="/history/{{ reading.sensor_id }}"
                    >
                        View temperature history →
                    </a>
                </section>
            {% endfor %}
        </div>
    {% else %}
        <p class="empty">No sensor readings found.</p>
    {% endif %}

    <footer class="server-info">
        Server:
        {{ server_info.hostname }}.local:5000
        &nbsp;|&nbsp;
        IP address:
        {{ server_info.ip_address }}
    </footer>

    <script>
        const unitButton =
            document.getElementById("unit-button");

        const temperatures =
            document.querySelectorAll(".temperature");

        let temperatureUnit =
            localStorage.getItem("temperatureUnit") || "C";

        function displayTemperatures() {
            temperatures.forEach(function (element) {
                const celsius = Number(
                    element.dataset.temperatureC
                );

                if (temperatureUnit === "F") {
                    const fahrenheit = (celsius * 9 / 5) + 32;

                    element.textContent =
                        fahrenheit.toFixed(2) + " °F";
                } else {
                    element.textContent =
                        celsius.toFixed(2) + " °C";
                }
            });

            unitButton.textContent =
                temperatureUnit === "C"
                    ? "Show °F"
                    : "Show °C";
        }

        unitButton.addEventListener("click", function () {
            temperatureUnit =
                temperatureUnit === "C" ? "F" : "C";

            localStorage.setItem(
                "temperatureUnit",
                temperatureUnit
            );

            displayTemperatures();
        });

        displayTemperatures();
    </script>
</body>
</html>
"""


SETTINGS_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>ClimateCube Settings</title>

    <style>
        body {
            margin: 0;
            padding: 30px;
            background: #eef2f6;
            color: #243447;
            font-family: Arial, sans-serif;
        }

        .page {
            max-width: 900px;
            margin: 0 auto;
        }

        .back-link {
            color: #243447;
            font-weight: bold;
            text-decoration: none;
        }

        .subtitle,
        .sensor-details,
        .last-reading {
            color: #667788;
        }

        .success,
        .error {
            margin: 18px 0;
            padding: 12px 16px;
            border-radius: 8px;
        }

        .success {
            background: #dff3e4;
            color: #236b35;
        }

        .error {
            background: #f9dddd;
            color: #8a2727;
        }

        .sensor-list {
            display: grid;
            gap: 16px;
            margin-top: 24px;
        }

        .sensor-card {
            padding: 22px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
        }

        .sensor-card h2 {
            margin-top: 0;
            margin-bottom: 8px;
        }

        .name-form {
            display: flex;
            gap: 10px;
            margin-top: 18px;
        }

        .name-form input {
            min-width: 0;
            flex: 1;
            padding: 11px 12px;
            border: 1px solid #b9c4ce;
            border-radius: 8px;
            color: #243447;
            font-size: 16px;
        }

        .name-form button {
            padding: 11px 18px;
            border: 0;
            border-radius: 8px;
            background: #243447;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }

        .last-reading {
            margin-bottom: 0;
            font-size: 13px;
        }

        @media (max-width: 600px) {
            body {
                padding: 18px;
            }

            .name-form {
                flex-direction: column;
            }
        }
    </style>
</head>

<body>
    <main class="page">
        <a class="back-link" href="/">← Current readings</a>

        <h1>Sensor settings</h1>
        <p class="subtitle">
            Give each ClimateCube a friendly location name.
        </p>

        {% if saved %}
            <p class="success">Sensor name updated.</p>
        {% endif %}

        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}

        {% if sensors %}
            <div class="sensor-list">
                {% for sensor in sensors %}
                    <section class="sensor-card">
                        <h2>{{ sensor.sensor_name }}</h2>

                        <div class="sensor-details">
                            Device: {{ sensor.device_id }}<br>
                            IP address: {{ sensor.ip_address or "Unknown" }}
                        </div>

                        <form
                            class="name-form"
                            method="post"
                            action="/settings/sensor/{{ sensor.sensor_id }}/name"
                        >
                            <input
                                type="text"
                                name="sensor_name"
                                value="{{ sensor.sensor_name }}"
                                maxlength="50"
                                required
                                aria-label="Friendly sensor name"
                            >

                            <button type="submit">Save name</button>
                        </form>

                        <p class="last-reading">
                            Last reading:
                            {{ sensor.last_reading_time or "No readings yet" }}
                        </p>
                    </section>
                {% endfor %}
            </div>
        {% else %}
            <p>No sensors have been discovered yet.</p>
        {% endif %}
    </main>
</body>
</html>
"""


HISTORY_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>{{ sensor.sensor_name }} History</title>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <style>
        body {
            margin: 0;
            padding: 30px;
            background: #eef2f6;
            color: #243447;
            font-family: Arial, sans-serif;
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
        }

        .back-link {
            color: #243447;
            font-weight: bold;
            text-decoration: none;
        }

        .controls {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 24px 0;
        }

        button {
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            background: #d8e0e8;
            color: #243447;
            font-size: 15px;
            cursor: pointer;
        }

        button.active,
        #unit-button {
            background: #243447;
            color: white;
        }

        .chart-card {
            height: 460px;
            padding: 22px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
        }

        .details,
        .status {
            color: #667788;
        }

        @media (max-width: 600px) {
            body {
                padding: 18px;
            }

            .chart-card {
                height: 360px;
                padding: 12px;
            }
        }
    </style>
</head>

<body>
    <a class="back-link" href="/">← Current readings</a>

    <div class="header">
        <div>
            <h1>{{ sensor.sensor_name }}</h1>
            <p class="details">
                Temperature history · {{ sensor.device_id }}
            </p>
        </div>

        <button id="unit-button" type="button">Show °F</button>
    </div>

    <div class="controls">
        <button class="range-button" data-range="6h">6 hours</button>
        <button class="range-button active" data-range="24h">24 hours</button>
        <button class="range-button" data-range="3d">3 days</button>
        <button class="range-button" data-range="7d">7 days</button>
    </div>

    <div class="chart-card">
        <canvas id="temperature-chart"></canvas>
    </div>

    <p id="status" class="status">Loading history...</p>

    <script>
        const sensorId = {{ sensor.sensor_id }};
        const unitButton = document.getElementById("unit-button");
        const rangeButtons = document.querySelectorAll(".range-button");
        const status = document.getElementById("status");
        let temperatureUnit =
            localStorage.getItem("temperatureUnit") || "C";
        let currentRange = "24h";
        let historyReadings = [];

        const chart = new Chart(
            document.getElementById("temperature-chart"),
            {
                type: "line",
                data: {
                    labels: [],
                    datasets: [{
                        label: "Temperature",
                        data: [],
                        borderColor: "#d35400",
                        backgroundColor: "rgba(211, 84, 0, 0.12)",
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.15,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: "index"
                    },
                    scales: {
                        x: {
                            ticks: { maxTicksLimit: 10 }
                        },
                        y: {
                            title: {
                                display: true,
                                text: "Temperature (°C)"
                            }
                        }
                    }
                }
            }
        );

        function updateChart() {
            const useFahrenheit = temperatureUnit === "F";

            chart.data.labels = historyReadings.map(function (reading) {
                return reading.reading_time.replace("T", " ");
            });

            chart.data.datasets[0].data = historyReadings.map(
                function (reading) {
                    const celsius = Number(reading.temperature_c);
                    return useFahrenheit
                        ? (celsius * 9 / 5) + 32
                        : celsius;
                }
            );

            chart.options.scales.y.title.text =
                "Temperature (°" + temperatureUnit + ")";
            unitButton.textContent =
                useFahrenheit ? "Show °C" : "Show °F";
            chart.update();
        }

        async function loadHistory() {
            status.textContent = "Loading history...";

            try {
                const response = await fetch(
                    "/api/history/" + sensorId + "?range=" + currentRange
                );

                if (!response.ok) {
                    throw new Error("History request failed");
                }

                const result = await response.json();
                historyReadings = result.readings;
                updateChart();
                status.textContent = historyReadings.length
                    ? historyReadings.length + " chart points"
                    : "No readings found for this period.";
            } catch (error) {
                status.textContent = "Unable to load temperature history.";
            }
        }

        rangeButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                rangeButtons.forEach(function (item) {
                    item.classList.remove("active");
                });

                button.classList.add("active");
                currentRange = button.dataset.range;
                loadHistory();
            });
        });

        unitButton.addEventListener("click", function () {
            temperatureUnit = temperatureUnit === "C" ? "F" : "C";
            localStorage.setItem("temperatureUnit", temperatureUnit);
            updateChart();
        });

        loadHistory();
    </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(
        DASHBOARD,
        readings=get_latest_readings(),
        server_info=get_server_info()
    )


@app.route("/api/latest")
def latest_api():
    return jsonify(get_latest_readings())


@app.route("/settings")
def settings():
    return render_template_string(
        SETTINGS_PAGE,
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

    return render_template_string(
        HISTORY_PAGE,
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
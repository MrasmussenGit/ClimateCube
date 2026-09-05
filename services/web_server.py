import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "data" / "climatecube.db"


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

        .unit-button {
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            background: #243447;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }

        .unit-button:hover {
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

        <button
            id="unit-button"
            class="unit-button"
            type="button"
        >
            Show °F
        </button>
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
                </section>
            {% endfor %}
        </div>
    {% else %}
        <p class="empty">No sensor readings found.</p>
    {% endif %}

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


@app.route("/")
def dashboard():
    return render_template_string(
        DASHBOARD,
        readings=get_latest_readings()
    )


@app.route("/api/latest")
def latest_api():
    return jsonify(get_latest_readings())


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
import sqlite3

from flask import Flask, jsonify

app = Flask(__name__)

DB_FILE = "data/climatecube.db"


@app.route("/")
def home():
    return "ClimateCube Web Server Running"


@app.route("/api/latest")
def latest():

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            s.sensor_id,
            s.sensor_name,
            r.temperature_c,
            r.humidity_pct,
            r.pressure_hpa,
            COALESCE(r.pico_ts, r.reading_ts) AS reading_time
        FROM sensor_reading r
        JOIN sensor s
            ON r.sensor_id = s.sensor_id
        WHERE r.reading_id IN
        (
            SELECT MAX(reading_id)
            FROM sensor_reading
            GROUP BY sensor_id
        )
        ORDER BY s.sensor_name
        """
    )

    rows = cursor.fetchall()

    conn.close()

    return jsonify(
        [dict(row) for row in rows]
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
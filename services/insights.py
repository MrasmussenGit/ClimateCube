import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


OUTDOOR_METRICS = {
    "temperature_c": {"label": "Outdoor temperature", "unit": "°C"},
    "humidity_pct": {"label": "Outdoor humidity", "unit": "%"},
    "dew_point_c": {"label": "Outdoor dew point", "unit": "°C"},
    "pressure_hpa": {"label": "Outdoor pressure", "unit": "hPa"},
    "precipitation_mm": {"label": "Precipitation", "unit": "mm"},
    "wind_speed_kmh": {"label": "Wind speed", "unit": "km/h"},
    "cloud_cover_pct": {"label": "Cloud cover", "unit": "%"}
}

LAG_MINUTES = range(0, 12 * 60 + 1, 15)
MIN_CORRELATION_SAMPLES = 12


def _finite(value):
    return value is not None and math.isfinite(float(value))


def _round(value, digits=3):
    return None if value is None else round(value, digits)


def _mean(values):
    return sum(values) / len(values)


def pearson(left, right):
    pairs = [
        (float(left_value), float(right_value))
        for left_value, right_value in zip(left, right)
        if _finite(left_value) and _finite(right_value)
    ]

    if len(pairs) < 3:
        return None

    left_values, right_values = zip(*pairs)
    left_mean = _mean(left_values)
    right_mean = _mean(right_values)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in pairs
    )
    left_variance = sum(
        (value - left_mean) ** 2
        for value in left_values
    )
    right_variance = sum(
        (value - right_mean) ** 2
        for value in right_values
    )
    denominator = math.sqrt(left_variance * right_variance)

    return numerator / denominator if denominator else None


def _ranks(values):
    ranked = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    position = 0

    while position < len(ranked):
        end = position + 1
        while end < len(ranked) and ranked[end][1] == ranked[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2
        for ranked_position in range(position, end):
            result[ranked[ranked_position][0]] = average_rank
        position = end

    return result


def spearman(left, right):
    pairs = [
        (float(left_value), float(right_value))
        for left_value, right_value in zip(left, right)
        if _finite(left_value) and _finite(right_value)
    ]

    if len(pairs) < 3:
        return None

    left_values, right_values = zip(*pairs)
    return pearson(_ranks(left_values), _ranks(right_values))


def _changes(observations, side, metric):
    changes = {}
    previous = None

    for observation in observations:
        values = observation.get(side)
        value = values.get(metric) if values else None
        timestamp = datetime.fromisoformat(observation["reading_time"])

        if _finite(value) and previous is not None:
            previous_time, previous_value = previous
            if (timestamp - previous_time).total_seconds() <= 1800:
                changes[timestamp] = float(value) - previous_value
        if _finite(value):
            previous = (timestamp, float(value))
        else:
            previous = None

    return changes


def _lag_analysis(observations, indoor_metric, outdoor_metric):
    indoor_changes = _changes(observations, "indoor", indoor_metric)
    outdoor_changes = _changes(observations, "outdoor", outdoor_metric)
    best = None

    for lag_minutes in LAG_MINUTES:
        lag_seconds = lag_minutes * 60
        indoor_values = []
        outdoor_values = []

        for indoor_time, indoor_value in indoor_changes.items():
            outdoor_time = indoor_time - timedelta(seconds=lag_seconds)
            if outdoor_time in outdoor_changes:
                indoor_values.append(indoor_value)
                outdoor_values.append(outdoor_changes[outdoor_time])

        correlation = pearson(outdoor_values, indoor_values)
        sample_count = len(indoor_values)

        if (
            correlation is not None
            and sample_count >= MIN_CORRELATION_SAMPLES
            and (
                best is None
                or abs(correlation) > abs(best["correlation"])
            )
        ):
            best = {
                "minutes": lag_minutes,
                "correlation": correlation,
                "sample_count": sample_count
            }

    return best


def _linear_fit(x_values, y_values):
    if len(x_values) < 3:
        return None

    x_mean = _mean(x_values)
    y_mean = _mean(y_values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)

    if denominator == 0:
        return None

    slope = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    ) / denominator
    intercept = y_mean - slope * x_mean

    return {
        "slope": slope,
        "intercept": intercept,
        "x_min": min(x_values),
        "x_max": max(x_values)
    }


def _sample_points(points, maximum=240):
    if len(points) <= maximum:
        return points

    step = (len(points) - 1) / (maximum - 1)
    return [
        points[round(index * step)]
        for index in range(maximum)
    ]


def _strength(correlation):
    if correlation is None:
        return "Unavailable"

    magnitude = abs(correlation)
    if magnitude >= 0.8:
        return "Very strong"
    if magnitude >= 0.6:
        return "Strong"
    if magnitude >= 0.4:
        return "Moderate"
    if magnitude >= 0.2:
        return "Modest"
    return "Weak"


def _solve_three_by_three(matrix, vector):
    augmented = [
        [float(value) for value in row] + [float(vector[index])]
        for index, row in enumerate(matrix)
    ]

    for column in range(3):
        pivot = max(
            range(column, 3),
            key=lambda row: abs(augmented[row][column])
        )
        if abs(augmented[pivot][column]) < 1e-12:
            return None
        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column]
        )
        divisor = augmented[column][column]
        augmented[column] = [
            value / divisor
            for value in augmented[column]
        ]

        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    augmented[row],
                    augmented[column]
                )
            ]

    return [augmented[row][3] for row in range(3)]


def _daily_pattern(observations, metric, timezone_info):
    samples = []

    for observation in observations:
        value = observation["indoor"].get(metric)
        if not _finite(value):
            continue
        timestamp = datetime.fromisoformat(
            observation["reading_time"]
        ).replace(tzinfo=timezone.utc).astimezone(timezone_info)
        hour = (
            timestamp.hour
            + timestamp.minute / 60
            + timestamp.second / 3600
        )
        angle = 2 * math.pi * hour / 24
        samples.append((float(value), math.sin(angle), math.cos(angle)))

    if len(samples) < MIN_CORRELATION_SAMPLES:
        return None

    matrix = [
        [len(samples), sum(sample[1] for sample in samples), sum(sample[2] for sample in samples)],
        [sum(sample[1] for sample in samples), sum(sample[1] ** 2 for sample in samples), sum(sample[1] * sample[2] for sample in samples)],
        [sum(sample[2] for sample in samples), sum(sample[1] * sample[2] for sample in samples), sum(sample[2] ** 2 for sample in samples)]
    ]
    vector = [
        sum(sample[0] for sample in samples),
        sum(sample[0] * sample[1] for sample in samples),
        sum(sample[0] * sample[2] for sample in samples)
    ]
    coefficients = _solve_three_by_three(matrix, vector)

    if coefficients is None:
        return None

    intercept, sine_coefficient, cosine_coefficient = coefficients
    observed = [sample[0] for sample in samples]
    fitted = [
        intercept
        + sine_coefficient * sample[1]
        + cosine_coefficient * sample[2]
        for sample in samples
    ]
    mean_value = _mean(observed)
    total_variation = sum((value - mean_value) ** 2 for value in observed)
    if total_variation == 0:
        return None
    residual_variation = sum(
        (value - estimate) ** 2
        for value, estimate in zip(observed, fitted)
    )
    r_squared = 1 - residual_variation / total_variation
    peak_angle = math.atan2(sine_coefficient, cosine_coefficient)
    if peak_angle < 0:
        peak_angle += 2 * math.pi

    return {
        "r_squared": _round(max(0, r_squared) if r_squared is not None else None),
        "amplitude": _round(math.hypot(sine_coefficient, cosine_coefficient)),
        "peak_hour": round(peak_angle * 24 / (2 * math.pi), 1),
        "sample_count": len(samples)
    }


def analyze_correlations(dataset, timezone_name="UTC"):
    observations = [
        observation
        for observation in dataset["observations"]
        if observation.get("outdoor") is not None
    ]
    try:
        timezone_info = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = "UTC"
        timezone_info = timezone.utc

    relationships = []

    for indoor_key, indoor_definition in dataset["indoor_metrics"].items():
        for outdoor_key, outdoor_definition in OUTDOOR_METRICS.items():
            points = []

            for observation in observations:
                indoor_value = observation["indoor"].get(indoor_key)
                outdoor_value = observation["outdoor"].get(outdoor_key)
                if _finite(indoor_value) and _finite(outdoor_value):
                    points.append({
                        "x": float(outdoor_value),
                        "y": float(indoor_value),
                        "t": observation["reading_time"]
                    })

            if len(points) < 3:
                continue

            x_values = [point["x"] for point in points]
            y_values = [point["y"] for point in points]
            indoor_changes = _changes(observations, "indoor", indoor_key)
            outdoor_changes = _changes(observations, "outdoor", outdoor_key)
            common_change_times = sorted(
                set(indoor_changes) & set(outdoor_changes)
            )
            change_correlation = pearson(
                [outdoor_changes[timestamp] for timestamp in common_change_times],
                [indoor_changes[timestamp] for timestamp in common_change_times]
            )
            lag = _lag_analysis(
                observations,
                indoor_key,
                outdoor_key
            )
            correlation = pearson(x_values, y_values)
            rank_correlation = spearman(x_values, y_values)

            if (
                correlation is None
                and rank_correlation is None
                and change_correlation is None
                and lag is None
            ):
                continue

            relationships.append({
                "id": f"{indoor_key}__{outdoor_key}",
                "indoor_key": indoor_key,
                "indoor_label": indoor_definition["label"],
                "indoor_unit": indoor_definition["unit"],
                "outdoor_key": outdoor_key,
                "outdoor_label": outdoor_definition["label"],
                "outdoor_unit": outdoor_definition["unit"],
                "pearson": _round(correlation),
                "spearman": _round(rank_correlation),
                "change_correlation": _round(change_correlation),
                "strength": _strength(correlation),
                "direction": (
                    "positive" if correlation is not None and correlation > 0
                    else "negative" if correlation is not None and correlation < 0
                    else "none"
                ),
                "sample_count": len(points),
                "lag": (
                    {
                        "minutes": lag["minutes"],
                        "correlation": _round(lag["correlation"]),
                        "sample_count": lag["sample_count"]
                    }
                    if lag else None
                ),
                "fit": {
                    key: _round(value)
                    for key, value in (_linear_fit(x_values, y_values) or {}).items()
                } or None,
                "points": _sample_points(points)
            })

    relationships.sort(
        key=lambda relationship: (
            abs(relationship["change_correlation"])
            if relationship["change_correlation"] is not None
            else -1,
            abs(relationship["pearson"])
            if relationship["pearson"] is not None
            else -1
        ),
        reverse=True
    )
    for relationship in relationships[4:]:
        relationship["points"] = []

    daily_patterns = []
    for metric, definition in dataset["indoor_metrics"].items():
        pattern = _daily_pattern(observations, metric, timezone_info)
        if pattern:
            daily_patterns.append({
                "metric": metric,
                "label": definition["label"],
                "unit": definition["unit"],
                **pattern
            })
    daily_patterns.sort(
        key=lambda pattern: pattern["r_squared"] or 0,
        reverse=True
    )

    sensor_count = dataset["sensor_bucket_count"]
    aligned_count = dataset["aligned_bucket_count"]
    coverage = aligned_count / sensor_count if sensor_count else 0
    duration_days = 0
    if len(observations) >= 2:
        duration_days = (
            datetime.fromisoformat(observations[-1]["reading_time"])
            - datetime.fromisoformat(observations[0]["reading_time"])
        ).total_seconds() / 86400

    warnings = [
        "Correlation does not establish causation. HVAC operation, occupancy, sunlight, open windows, and sensor placement are not measured confounders.",
        "Closely spaced sensor readings are autocorrelated, so ordinary correlation sample counts overstate independent evidence.",
        "The reported lag is the strongest candidate tested from 0 to 12 hours; searching many lags can make the winning correlation look stronger than it will be on new data.",
        "This is exploratory analysis across many metric pairs; isolated strong results should be confirmed over another time period."
    ]
    if duration_days < 7:
        warnings.insert(
            0,
            "Less than seven days of aligned data is available; daily patterns and lag estimates are preliminary."
        )
    if coverage < 0.8:
        warnings.insert(
            0,
            "Fewer than 80% of indoor time buckets have a nearby outdoor observation."
        )
    if aligned_count < 96:
        warnings.insert(
            0,
            "Fewer than 96 aligned observations are available; correlation estimates are unstable."
        )

    return {
        "timezone": timezone_name,
        "coverage": {
            "sensor_buckets": sensor_count,
            "aligned_buckets": aligned_count,
            "aligned_percent": round(coverage * 100, 1),
            "duration_days": round(duration_days, 1)
        },
        "relationships": relationships,
        "daily_patterns": daily_patterns,
        "warnings": warnings
    }

import math
from datetime import datetime, timezone
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


def _pearson_pairs(pairs):
    count = 0
    left_mean = 0.0
    right_mean = 0.0
    left_variation = 0.0
    right_variation = 0.0
    co_moment = 0.0

    for left_value, right_value in pairs:
        count += 1
        left_delta = left_value - left_mean
        left_mean += left_delta / count
        right_delta = right_value - right_mean
        right_mean += right_delta / count
        left_variation += left_delta * (left_value - left_mean)
        right_variation += right_delta * (right_value - right_mean)
        co_moment += left_delta * (right_value - right_mean)

    denominator = math.sqrt(left_variation * right_variation)
    correlation = (
        co_moment / denominator
        if count >= 3 and denominator
        else None
    )
    return correlation, count


def pearson(left, right):
    correlation, _ = _pearson_pairs(
        (float(left_value), float(right_value))
        for left_value, right_value in zip(left, right)
        if _finite(left_value) and _finite(right_value)
    )
    return correlation


def _pearson_clean(left, right):
    correlation, _ = _pearson_pairs(zip(left, right))
    return correlation


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
    return _pearson_clean(_ranks(left_values), _ranks(right_values))


def _changes(observations, timestamps, side, metric):
    changes = {}
    previous = None

    for observation, timestamp in zip(observations, timestamps):
        values = observation.get(side)
        value = values.get(metric) if values else None

        if _finite(value) and previous is not None:
            previous_time, previous_value = previous
            if (timestamp - previous_time).total_seconds() <= 1800:
                bucket = int(
                    timestamp.replace(tzinfo=timezone.utc).timestamp()
                    // (15 * 60)
                )
                changes[bucket] = float(value) - previous_value
        if _finite(value):
            previous = (timestamp, float(value))
        else:
            previous = None

    return changes


def _dense_changes(changes, first_bucket, bucket_count):
    values = [None] * bucket_count
    for bucket, value in changes.items():
        values[bucket - first_bucket] = value
    return values


def _lag_analysis(indoor_changes, outdoor_changes):
    best = None

    for lag_minutes in LAG_MINUTES:
        lag_buckets = lag_minutes // 15
        sample_count = 0
        outdoor_sum = 0.0
        indoor_sum = 0.0
        outdoor_squared_sum = 0.0
        indoor_squared_sum = 0.0
        product_sum = 0.0

        for outdoor_index in range(len(outdoor_changes) - lag_buckets):
            outdoor_value = outdoor_changes[outdoor_index]
            indoor_value = indoor_changes[outdoor_index + lag_buckets]
            if outdoor_value is None or indoor_value is None:
                continue
            sample_count += 1
            outdoor_sum += outdoor_value
            indoor_sum += indoor_value
            outdoor_squared_sum += outdoor_value * outdoor_value
            indoor_squared_sum += indoor_value * indoor_value
            product_sum += outdoor_value * indoor_value

        numerator = sample_count * product_sum - outdoor_sum * indoor_sum
        denominator = math.sqrt(
            max(
                0.0,
                sample_count * outdoor_squared_sum - outdoor_sum ** 2
            )
            * max(
                0.0,
                sample_count * indoor_squared_sum - indoor_sum ** 2
            )
        )
        correlation = numerator / denominator if denominator else None

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


def analyze_correlations(
    dataset,
    timezone_name="UTC",
    indoor_keys=None,
    outdoor_keys=None,
    include_daily_patterns=True
):
    observations = [
        observation
        for observation in dataset["observations"]
        if observation.get("outdoor") is not None
    ]
    indoor_metrics = {
        key: definition
        for key, definition in dataset["indoor_metrics"].items()
        if indoor_keys is None or key in indoor_keys
    }
    outdoor_metrics = {
        key: definition
        for key, definition in OUTDOOR_METRICS.items()
        if outdoor_keys is None or key in outdoor_keys
    }
    try:
        timezone_info = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = "UTC"
        timezone_info = timezone.utc

    timestamps = [
        datetime.fromisoformat(observation["reading_time"])
        for observation in observations
    ]
    indoor_change_maps = {
        metric: _changes(observations, timestamps, "indoor", metric)
        for metric in indoor_metrics
    }
    outdoor_change_maps = {
        metric: _changes(observations, timestamps, "outdoor", metric)
        for metric in outdoor_metrics
    }
    populated_change_maps = [
        changes
        for changes in (
            list(indoor_change_maps.values())
            + list(outdoor_change_maps.values())
        )
        if changes
    ]
    first_bucket = min(
        (min(changes) for changes in populated_change_maps),
        default=0
    )
    final_bucket = max(
        (max(changes) for changes in populated_change_maps),
        default=-1
    )
    bucket_count = max(0, final_bucket - first_bucket + 1)
    indoor_change_cache = {
        metric: _dense_changes(changes, first_bucket, bucket_count)
        for metric, changes in indoor_change_maps.items()
    }
    outdoor_change_cache = {
        metric: _dense_changes(changes, first_bucket, bucket_count)
        for metric, changes in outdoor_change_maps.items()
    }
    relationships = []

    for indoor_key, indoor_definition in indoor_metrics.items():
        for outdoor_key, outdoor_definition in outdoor_metrics.items():
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
            indoor_changes = indoor_change_cache[indoor_key]
            outdoor_changes = outdoor_change_cache[outdoor_key]
            change_correlation = pearson(
                outdoor_changes,
                indoor_changes
            )
            lag = _lag_analysis(indoor_changes, outdoor_changes)
            correlation = _pearson_clean(x_values, y_values)
            rank_correlation = _pearson_clean(
                _ranks(x_values),
                _ranks(y_values)
            )

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
    if include_daily_patterns:
        for metric, definition in indoor_metrics.items():
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

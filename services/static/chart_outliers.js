(function () {
    "use strict";

    function median(values) {
        if (!values.length) return 0;
        const sorted = values.slice().sort(function (left, right) {
            return left - right;
        });
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2
            ? sorted[middle]
            : (sorted[middle - 1] + sorted[middle]) / 2;
    }

    function filter(values, enabled) {
        const filtered = values.slice();

        if (!enabled) return { values: filtered, count: 0 };

        const points = values
            .map(function (value, index) {
                const numericValue = Number(value);
                return value === null || value === undefined || !Number.isFinite(numericValue)
                    ? null
                    : { index: index, value: numericValue };
            })
            .filter(function (point) { return point !== null; });

        if (points.length < 3) return { values: filtered, count: 0 };

        const steps = points.slice(1).map(function (point, index) {
            return Math.abs(point.value - points[index].value);
        });
        const typicalStep = median(steps);
        const typicalMagnitude = median(points.map(function (point) {
            return Math.abs(point.value);
        }));
        const minimumDeviation = Math.max(
            typicalStep * 6,
            typicalMagnitude * 0.01,
            1e-9
        );
        const neighborTolerance = Math.max(
            typicalStep * 3,
            typicalMagnitude * 0.005,
            1e-9
        );
        let count = 0;

        for (let position = 1; position < points.length - 1; position += 1) {
            const previous = points[position - 1].value;
            const current = points[position].value;
            const next = points[position + 1].value;
            const expected = (previous + next) / 2;

            if (
                Math.abs(previous - next) <= neighborTolerance &&
                Math.abs(current - expected) >= minimumDeviation
            ) {
                filtered[points[position].index] = null;
                count += 1;
            }
        }

        return { values: filtered, count: count };
    }

    window.ClimateCubeOutliers = { filter: filter };
}());

def mean(values):
    if not values:
        raise ValueError("mean of an empty sequence")
    return sum(values) / len(values)


def median(values):
    if not values:
        raise ValueError("median of an empty sequence")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def clamp(value, low, high):
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))


def normalize(values):
    low, high = min(values), max(values)
    if low == high:
        return [0.0 for _ in values]
    span = high - low
    return [(value - low) / span for value in values]


def moving_average(values, window):
    if window < 1:
        raise ValueError("window must be at least 1")
    result = []
    running = 0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        result.append(running / min(index + 1, window))
    return result

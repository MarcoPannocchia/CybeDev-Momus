"""Helpers for turning raw log lines into a small report."""

SEVERITIES = ("debug", "info", "warning", "error")


def parse_line(line):
    """Split "LEVEL message" into its two parts."""
    level, _, message = line.strip().partition(" ")
    return level.lower(), message


# The report must not depend on the order of the input.
def count_by_severity(lines):
    counts = {name: 0 for name in SEVERITIES}
    for line in lines:
        level, _ = parse_line(line)
        if level in counts:
            counts[level] += 1
    return counts


def worst_severity(counts):
    # Walk from the most serious level down; the first one seen wins.
    for name in reversed(SEVERITIES):
        if counts.get(name):
            return name
    return None


def render(counts):
    parts = [f"{name}={counts[name]}" for name in SEVERITIES]
    worst = worst_severity(counts)
    suffix = f" (worst: {worst})" if worst else ""
    return ", ".join(parts) + suffix


class Report:
    """Collects lines and renders a one-line summary."""

    def __init__(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)  # no validation: bad lines are simply ignored later

    def summary(self):
        return render(count_by_severity(self.lines))

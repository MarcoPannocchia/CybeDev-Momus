import re

_WORD = re.compile(r"[a-z0-9']+")


def tokenize(text):
    return _WORD.findall(text.lower())


def word_frequencies(text):
    counts = {}
    for word in tokenize(text):
        counts[word] = counts.get(word, 0) + 1
    return counts


def top_words(text, limit=3):
    counts = word_frequencies(text)
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [word for word, _ in ranked[:limit]]


def truncate(text, width, marker="..."):
    if width < len(marker):
        raise ValueError("width is smaller than the marker")
    if len(text) <= width:
        return text
    return text[: width - len(marker)].rstrip() + marker


def is_palindrome(text):
    letters = [char for char in text.lower() if char.isalnum()]
    return letters == letters[::-1]


def wrap(text, width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines

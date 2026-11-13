"""Cheap, deterministic quality rules for what a model wrote.

Small models produce a lot of text that is correct but useless: a comment that
says "This checks if the list is empty" above exactly that check, a
``Returns: None`` section, a placeholder like "the comment text is missing".
Argus cannot see any of it, because it only proves the code is unchanged, and
asking the strong model to flag it costs tokens. These rules catch the
obvious cases for free.

They are heuristics. They can throw away a comment that was fine, and that is
the safe direction: Momus would rather add fewer comments than add noise.
Nothing here reads or changes code; it only judges and cleans text.
"""

import re

# --- Docstrings ------------------------------------------------------------

# Heading spellings models use, and the one they are folded into.
_HEADINGS = {
    "args": "Args",
    "arguments": "Args",
    "parameters": "Args",
    "params": "Args",
    "return": "Returns",
    "returns": "Returns",
    "return value": "Returns",
    "return values": "Returns",
    "raises": "Raises",
    "exceptions": "Raises",
    "yield": "Yields",
    "yields": "Yields",
    "attributes": "Attributes",
}
# Sections that only list what the code already shows; they are removed.
_DROPPED_HEADINGS = {
    "methods",
    "method",
    "static method",
    "static methods",
    "class method",
    "class methods",
    "properties",
}
# Other headings that only get a blank line before and an indent after.
_OTHER_HEADINGS = {"example": "Example", "examples": "Examples", "note": "Note", "notes": "Notes"}

_HEADING_LINE = re.compile(r"^([A-Za-z ]+):\s*(.*)$")
_BULLET = re.compile(r"^(\s*)[-*•]\s+")
_BACKTICKED_NAME = re.compile(r"^(\s*)`([^`]+)`")
# Entries that say nothing: "None", "No exceptions are raised", "self: ...".
_VACUOUS = re.compile(
    r"^(none|n/?a|nothing|no exceptions?( (are|is|will be))?( raised| thrown)?|"
    r"does not (raise|return)( anything| any exceptions?)?)\.?$",
    re.IGNORECASE,
)
_SELF_ENTRY = re.compile(r"^(self|cls)\b[^:]*:", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`])")
# The reply repeats the instructions instead of answering them.
_TEMPLATE = re.compile(r"^<[^>]*>$|\b(the (docstring|comment) text|comment text is missing)\b", re.IGNORECASE)
# A docstring too long for one line gets its first sentence as a summary line.
SUMMARY_LIMIT = 72


def is_placeholder(text: str) -> bool:
    """Tell whether ``text`` is the template echoed back, not an answer."""
    return bool(_TEMPLATE.search(text.strip()))


def _normalized(text: str) -> str:
    """Lower-case ``text`` and reduce it to words separated by single spaces."""
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def copied_from_instructions(text: str, instructions: str) -> bool:
    """Tell whether a sentence of ``text`` is lifted from ``instructions``.

    Small models sometimes paste part of their prompt into the answer: an
    example, or the sentence that gave them context. Such text is about the
    prompt, not about the code, so it is false wherever it lands. A sentence of
    four words or more that appears word for word in the instructions counts.
    """
    source = f" {_normalized(instructions)} "
    for sentence in re.split(r"[.!?\n]+", text):
        words = _normalized(sentence)
        if len(words.split()) >= 4 and f" {words} " in source:
            return True
    return False


def _is_vacuous(line: str) -> bool:
    stripped = line.strip()
    return bool(_VACUOUS.match(stripped) or _SELF_ENTRY.match(stripped))


def polish_docstring(text: str) -> str:
    """Clean a docstring's text without changing what it says.

    Section headings on a line of their own get one spelling (``Args``,
    ``Returns``, ``Raises``) and a blank line before them; their entries lose
    bullets and backticks around the name and are indented. Entries that say
    nothing (``None``, "no exceptions", the ``self`` argument) are dropped, and
    a section left empty goes with them. A list of the class's methods is
    removed. Plain paragraphs are joined into single lines, to be wrapped evenly
    later. A long single paragraph is split after its first sentence so there
    is a summary line. A heading with its text on
    the same line (``Returns: the value.``) is left alone, unless that text
    says nothing.
    """
    out: list[str] = []
    section: str | None = None  # the heading we are inside, if any
    kind = ""  # "entries" (Args, Returns, ...) or "other" (Example, Note)
    body: list[str] = []

    def close() -> None:
        nonlocal section, kind, body
        if section is not None and kind != "drop":
            kept = [line for line in body if not (kind == "entries" and _is_vacuous(line))]
            if any(line.strip() for line in kept):
                if out and out[-1] != "":
                    out.append("")
                out.append(f"{section}:")
                out.extend(kept)
        section, kind, body = None, "", []

    for line in text.split("\n"):
        heading = None if line[:1].isspace() else _HEADING_LINE.match(line)
        name = heading.group(1).strip().lower() if heading else ""
        rest = heading.group(2).strip() if heading else ""
        if heading and name in _HEADINGS:
            close()
            if not rest:
                section, kind = _HEADINGS[name], "entries"
            elif not _is_vacuous(rest):
                out.append(line)
        elif heading and name in _OTHER_HEADINGS and not rest:
            close()
            section, kind = _OTHER_HEADINGS[name], "other"
        elif heading and name in _DROPPED_HEADINGS and not rest:
            close()
            section, kind = name, "drop"
        elif section is not None and not line.strip():
            close()
            out.append("")
        elif section is not None:
            entry = line
            if kind == "entries":
                entry = _BACKTICKED_NAME.sub(r"\1\2", _BULLET.sub(r"\1", entry))
            body.append(entry if entry[:1] in (" ", "\t") else "    " + entry)
        else:
            out.append(line)
    close()
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")
    # A last line such as "Example usage:" with nothing after it promises
    # content that never came.
    text = re.sub(r"\n+[^\n]{0,40}:\s*$", "", text) if "\n" in text else text
    return _add_summary_line(_reflow(text))


def _reflow(text: str) -> str:
    """Join the lines of each plain paragraph into one line.

    Models break lines wherever they like; wrapping such text again gives
    ragged lines. Sections, indented lines, list items and a heading with its
    text on the same line are left as they are.
    """
    paragraphs = []
    for paragraph in text.split("\n\n"):
        lines = paragraph.split("\n")
        special = any(
            line[:1].isspace() or _BULLET.match(line) or re.match(r"\d+[.)]\s", line) for line in lines
        ) or lines[0].rstrip().endswith(":")
        if special:
            paragraphs.append(paragraph)
            continue
        joined: list[str] = []
        for line in lines:
            heading = _HEADING_LINE.match(line)
            inline_heading = heading and heading.group(1).strip().lower() in _HEADINGS
            if joined and not inline_heading and not joined[-1].startswith("\0"):
                joined[-1] += " " + line.strip()
            else:
                joined.append(("\0" if inline_heading else "") + line.strip())
        paragraphs.append("\n".join(line.lstrip("\0") for line in joined))
    return "\n\n".join(paragraphs)


def _add_summary_line(text: str) -> str:
    """Split ``text`` after its first sentence if that paragraph is long and single."""
    first, separator, rest = text.partition("\n\n")
    if "\n" in first or len(first) <= SUMMARY_LIMIT:
        return text
    sentences = _SENTENCE_END.split(first, maxsplit=1)
    if len(sentences) < 2:
        return text
    summary, remainder = sentences
    return f"{summary}\n\n{remainder}" + (separator + rest if separator else "")


# --- Inline comments -------------------------------------------------------

# "This function ..." and "The `retry` function ...": a description, not a reason.
_DESCRIPTIVE_OPENER = re.compile(
    r"^(this|the|these)\s+(`[^`]+`\s+|\w+\s+)?(function|method|class|code|statement|line|lines|snippet)\b"
    # "This checks ...", "It returns ...": a verb saying what the line does.
    r"|^(this|it)\s+(checks?|ensures?|calculates?|computes?|iterates?|loops?|returns?|raises?|sorts?|"
    r"sets?|creates?|initiali[sz]es?|updates?|adds?|removes?|stores?|gets?|handles?|verif(y|ies)|"
    r"validates?|assigns?|defines?|retrieves?|converts?)\b",
    re.IGNORECASE,
)
# Other ways a comment narrates instead of explaining:
#   "This list comprehension creates ..."   ("This" + a noun, unless it gives a reason)
#   "The `x` ..." / "The condition `x` ..."  (the code quoted back)
#   "If the list is empty, it raises ..."    ("If ..., it ...")
#   "Otherwise, it returns ..."
# "This is needed because ...", "This avoids ..." give a reason and are kept.
_NARRATION = re.compile(
    r"^this\s+(?!(is|was|avoids?|prevents?|keeps?|lets?|allows?|guards?|protects?|"
    r"stops?|means|way|must|should|needs?|has to|exists?)\b)\w+"
    r"|^the\s+(\w+\s+){0,2}`[^`]+`"
    r"|^(if|when|while|for each|after|before)\b[^,]{3,80},\s*(it|we)\b"
    r"|^(otherwise|then|next|finally),?\s+(it|we)\b"
    r"|^it\s+\w+s\b",
    re.IGNORECASE,
)
# "Initialize the range of values.": an instruction that says what the line does.
_IMPERATIVE = re.compile(
    r"^(initiali[sz]e|calculate|compute|check|loop|iterate|return|set|create|sort|update|add|remove|"
    r"get|define|assign|store|append|increment|decrement|convert|call|raise|find|build|join|split|"
    r"filter|extract|handle|catch|print|read|write|open|close|sum|count|apply|reset|clear|determine|"
    r"ensure|verify|validate|format|parse|generate|retrieve|fetch|load|save|delete|insert|combine|"
    r"concatenate|truncate|strip|replace|collect|record|track|skip|yield|declare|construct|populate|"
    r"copy|select|compare|accumulate|adjust|normali[sz]e|wrap|use|make|run|execute|perform)s?\b",
    re.IGNORECASE,
)
# Words that show a comment gives a reason and not only a description.
_REASON = re.compile(
    r"\b(so|because|since|otherwise|unless|avoids?|prevents?|needs?|must|would|in case|instead|"
    r"rather than|in order to|guarantees?|requires?|required|"
    r"to (keep|avoid|prevent|make sure|allow|let|stop|protect|guard))\b|[:;]",
    re.IGNORECASE,
)
# "The mean is calculated by dividing ...": the passive voice of narration.
_PASSIVE = re.compile(
    r"\b(is|are|gets?)\s+(then\s+|first\s+|also\s+)?(calculated|computed|obtained|set|decremented|"
    r"incremented|updated|removed|added|returned|sorted|initiali[sz]ed|created|checked|used|stored|"
    r"appended|adjusted|determined|assigned|converted|formatted|joined|raised|called|passed)\b",
    re.IGNORECASE,
)
# "The loop iterates over each line ...": a subject and a verb that narrate.
_NARRATING_VERB = re.compile(
    r"\b(returns|iterates|loops|checks|appends|adds|creates|calculates|computes|sets|updates|removes|"
    r"raises|calls|sorts|stores|extracts|parses|formats|joins|converts|initiali[sz]es|assigns|"
    r"increments|decrements|processes|handles|takes|retrieves|determines|verifies)\b",
    re.IGNORECASE,
)
# An inline comment longer than this is a paragraph of narration.
MAX_COMMENT_CHARS = 160
_WORD = re.compile(r"[a-z][a-z0-9]{2,}")
_STOPWORDS = frozenset(
    "the and for with that this from when are was will then into each all any can not its has have "
    "been being which while also else only than over under both same must should would could "
    "you your our out but one two use used using where what here there".split()
)
# What a keyword means in words, so that "loop over the values" counts as
# restating a ``for`` line.
_KEYWORD_WORDS = {
    "for": "loop loops iterate iterates each every",
    "while": "loop loops repeat repeats",
    "if": "check checks whether verify verifies",
    "return": "return returns returned",
    "raise": "raise raises throw throws error",
    "try": "try tries attempt attempts",
    "except": "catch catches handle handles",
    "assert": "assert asserts ensure ensures",
    "with": "open opens context",
    "import": "import imports",
}
RESTATE_RATIO = 0.6
MIN_WORDS = 2


def _stem(word: str) -> str:
    """Cut a word down to a rough stem, so "sorted", "sorts" and "sort" meet.

    Crude on purpose: it only has to be the same on both sides of a comparison.
    """
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def _words(text: str) -> set[str]:
    """Stemmed content words of ``text``, with identifiers also split into their parts."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ")
    found = set(_WORD.findall(text.lower())) | set(_WORD.findall(spaced.lower()))
    return {_stem(word) for word in found - _STOPWORDS}


def comment_problem(text: str, statement: str) -> str | None:
    """Return why a comment above ``statement`` should be dropped, or None.

    Dropped: placeholders; comments that narrate ("This checks ...", "The `x`
    ...", "If ..., it ...", "Otherwise, it ..."); bare instructions and
    passive descriptions with no reason ("Initialize the total.", "The total
    is calculated ..."); comments longer than a couple of lines; and comments whose words are mostly found in the statement
    itself, which only say again what the code says.
    """
    if is_placeholder(text):
        return "the comment is a placeholder"
    stripped = text.strip()
    if _DESCRIPTIVE_OPENER.match(stripped) or _NARRATION.match(stripped):
        return "the comment describes the code instead of explaining it"
    describes = _IMPERATIVE.match(stripped) or _PASSIVE.search(stripped) or _NARRATING_VERB.search(stripped)
    if describes and not _REASON.search(stripped):
        return "the comment says what the code does, with no reason"
    if len(stripped) > MAX_COMMENT_CHARS:
        return "the comment is too long for an inline comment"
    words = _words(text)
    if len(words) < MIN_WORDS:
        return None
    vocabulary = _words(statement)
    for keyword in re.findall(r"[A-Za-z_]+", statement):
        vocabulary |= _words(_KEYWORD_WORDS.get(keyword, ""))
    if len(words & vocabulary) / len(words) >= RESTATE_RATIO:
        return "the comment only repeats the statement it is above"
    return None

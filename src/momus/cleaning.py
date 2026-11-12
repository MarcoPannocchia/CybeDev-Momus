"""Cleans a model's raw reply before anything else looks at it.

Local models often wrap their answer: a markdown fence, a sentence before or
after it ("Here is the code..."), or a ``<think>`` block from a reasoning
model. This module removes that wrapping and nothing else.

Cleaning is not a safety step. It only makes a good answer usable; Argus
still decides whether the result is accepted.
"""

import re

# A reasoning block, closed or cut off (the model ran out of tokens while
# thinking, so nothing after the tag is an answer).
_THINK_BLOCK = re.compile(r"<think>.*?(?:</think>|\Z)", re.DOTALL | re.IGNORECASE)
# Some servers strip the opening tag and leave only the closing one.
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)

# A fenced block: an opening line of three backticks with an optional language
# name, then everything up to a closing fence line. If the reply was cut off
# before the closing fence, the block runs to the end of the text.
_FENCE = re.compile(
    r"^[ \t]*```[^\n`]*\n(?P<body>.*?)(?:^[ \t]*```[ \t]*$|\Z)",
    re.DOTALL | re.MULTILINE,
)


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks, and anything before an orphan ``</think>``.

    Raises:
        TypeError: if ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise TypeError(f"model output must be text, got {type(text).__name__}")
    text = _THINK_BLOCK.sub("", text)
    stray_close = None
    for stray_close in _THINK_CLOSE.finditer(text):
        pass
    if stray_close is not None:
        # Everything up to the last orphan closing tag was reasoning.
        text = text[stray_close.end() :]
    return text


def clean_output(text: str) -> str:
    """Return the useful part of a model reply, without its wrapping.

    Reasoning blocks are dropped first. Then, if the reply contains a fenced
    block, only the inside of the first one is kept, exactly as written: this
    is what removes the chatter around it. Without a fence nothing can be
    told apart from the answer, so only blank lines at the edges are trimmed
    and a single sentence of chatter is left for the guard to reject.

    Raises:
        TypeError: if ``text`` is not a string.
    """
    text = strip_reasoning(text)

    fenced = _FENCE.search(text)
    if fenced is not None:
        return fenced.group("body")

    # Leading blank lines go, but not the first line's own indentation.
    return re.sub(r"\A(?:[ \t]*\n)+", "", text).rstrip()

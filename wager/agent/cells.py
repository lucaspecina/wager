"""Extract the Python cell from a model reply.

The model is told to put exactly one runnable cell in a ```python fence. We take
the first python-fenced block; failing that, the first generic fence.
"""

import re

_PY_FENCE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.DOTALL)
_ANY_FENCE = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def extract_cell(text: str) -> str | None:
    m = _PY_FENCE.search(text)
    if m:
        return m.group(1).strip()
    m = _ANY_FENCE.search(text)
    if m:
        return m.group(1).strip()
    return None

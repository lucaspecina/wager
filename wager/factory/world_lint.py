"""Factory validator: import lint for world.py (Decision Log v0.10).

world.py must stay loadable server-side AND scoreable as the S_truth anchor
through the same sandbox as any submission, so it passes the full submission
lint with a stricter import allowlist: numpy/pandas/scipy/safe-stdlib, no
subprocess/os/network.
"""

from wager.reward.sandbox import lint_submission

ALLOWED_WORLD_IMPORTS = {
    "numpy",
    "pandas",
    "scipy",
    "math",
    "statistics",
    "itertools",
    "functools",
    "collections",
}


def lint_world(source: str) -> None:
    lint_submission(source, allowlist=ALLOWED_WORLD_IMPORTS)

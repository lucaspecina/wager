"""Human-inspection report generator (tooling, not the reward path).

Builds a single self-contained HTML report for a case + an episode trace, so a
human can audit end to end: the world and its trap (the answer key), the brief the
agent sees, the secret battery, the agent's full trajectory (reasoning, code,
outputs, submission), and how the grade was computed item by item. This is the
loop-maestro inspection surface (NORTH_STAR §3).
"""

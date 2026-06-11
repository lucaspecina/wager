"""The agent / solver side: LLM clients and cell parsing.

LLM use is allowed HERE (the solver is the thing being measured, not the reward).
This package MUST NEVER be imported by wager.reward (the zero-LLM reward path);
the CI gate enforces that on the reward side.
"""

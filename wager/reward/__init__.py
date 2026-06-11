"""The reward path. ZERO-LLM ZONE (NORTH_STAR 2.2, temporal frontier).

Everything importable from this package runs between episode start and reward
emission. CI enforces a strict import allowlist (tests/test_zero_llm_ci.py):
stdlib-safe + numpy/pandas/scipy + wager.contracts. No LLM clients, no network.
Production scoring always runs with the sandbox network disabled, not only CI.
"""

"""WAGER - Worlds As Generators of Epistemic Reward.

Package layout (see ARCHITECTURE.md):
- wager.contracts: Pydantic contracts shared by factory and reward path.
- wager.reward: the reward path. STRICT import allowlist (stdlib + numpy/pandas/scipy
  + wager.contracts). No LLM clients, no network. Enforced by CI (ARCHITECTURE 13-L0).
- wager.factory: design-time machinery (case loading, validators; later: rivals,
  battery derivation, digestion). LLM use allowed here, never at episode/scoring time.
"""

__version__ = "0.1.0"

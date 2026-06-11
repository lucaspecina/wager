"""Seed semantics of the scoring pipeline (Decision Log v0.10).

World side: one seed per battery item, persisted in battery.json, shared by
every submission (common random numbers). Model side: derived deterministically
per repetition and NEVER equal to the world seed - if they coincided,
submitting world.py verbatim would yield D == 0 exactly and the S_truth
ceiling would lose its sampling-noise semantics.
"""

import hashlib


def _hash_to_seed(tag: str) -> int:
    # 32-bit so the seed is accepted by BOTH numpy RNG APIs: the modern
    # np.random.default_rng(seed) (any int) AND the legacy np.random.seed(seed)
    # which requires [0, 2**32 - 1]. A 64-bit seed silently crashed legacy-API
    # submissions on every battery item (E0.5 DeepSeek diagnostic, Decision Log
    # v0.16) -- an instrument artifact, not a skill gap. The instrument must be
    # agnostic to a submission's legitimate RNG choice.
    digest = hashlib.sha256(tag.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def derive_seed(seed_world: int, rep: int) -> int:
    """Model-side seed for repetition `rep` of a battery item."""
    return _hash_to_seed(f"wager:model-side:{seed_world}:{rep}")


def derive_null_seed(seed_world: int) -> int:
    """Seed for the per-item null (column permutation) used by D_MAX."""
    return _hash_to_seed(f"wager:item-null:{seed_world}")


def derive_world_seed(base: int, item_index: int, resample: int) -> int:
    """World-side seed for L2 resampled seed-sets (resample >= 1).

    Production seed-sets are the ones persisted in battery.json; this is only
    for the L2 variance protocol (and, in E2, periodic seed rotation).
    """
    return _hash_to_seed(f"wager:world-side:{base}:{item_index}:{resample}")

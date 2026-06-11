"""Interactive episode harness: persistent kernel + env verbs + budget ledger.

Server / factory side. The kernel runs the agent's Python cells; the env proxies
the world's verbs. In Slice 2 / C1 this is a minimal in-process version to
de-risk the LLM plumbing first ("integration-first", Decision Log v0.14); the
opaque handle (world in a separate process, data-only IPC) and the full verb set
(experiment/submit) land in checkpoint C3, with their hardening gaps tracked in
REDTEAM.md. Never imported by wager.reward.
"""

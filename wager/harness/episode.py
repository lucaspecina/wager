"""Drive one LLM episode: model <-> opaque kernel <-> WorldServer.

Applies the runaway guards (Decision Log v0.14, precision 2), builds the
re-readable per-turn trace (precision 4), logs failed submits with their
actionable error (precision 3), and records the E0.5 signal: was experiment()
paid BEFORE or AFTER the agent voiced a confounding suspicion (precision 5,
an embryo of the E1/E2 signatures -- keyword heuristic, flagged as such).
"""

import json

from wager.agent.cells import extract_cell
from wager.agent.llm_client import FoundryChat
from wager.harness.kernel_proc import KernelClient
from wager.harness.world_server import WorldServer

# Runaway guards (v0 defaults, Decision Log v0.14). The token cap doubles as the
# $ guard: $ ~ tokens x rate, with the rate not wired -- tokens ARE the budget.
MAX_TURNS = 25
MAX_TOKENS = 200_000
MAX_COMPLETION_TOKENS = 6000
CELL_TIMEOUT_S = 30.0

SYSTEM = """You are an investigator modelling an unknown system through a Python REPL, on a budget.
Work by writing ONE Python cell per reply, always inside a ```python fenced block. The kernel runs
it and returns stdout, so PRINT what you want to see; variables persist across cells. `env` provides:
  env.describe()                      -> dict (free)
  env.observe(source, n)              -> DataFrame (debits cost/row)
  env.experiment(config=..., context=..., n=...) -> DataFrame (debits fixed + cost/row);
        config fixes knobs, e.g. config={"dose": 4.0}; context targets a population, e.g. {"cohort": 1.0}
  env.submit(code_string)             -> result with .accepted and .error
Spend the budget wisely. When confident, build your model program (a string defining
model(regime, n, seed)) and call env.submit(code). If it fails validation, read .error, fix, resubmit.
Keep prose to a one-line plan; put the work in the cell. For big DataFrames print .head() and .shape."""

_SUSPICION = (
    "confound", "causal", "spurious", "intervention", "intervene", "stratif",
    "selection bias", "indication", "backdoor", "back-door", "collider",
    "do(dose", "do-operator", "not causal", "reverse caus",
)


def _suspicion_in(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _SUSPICION)


def run_episode(
    server: WorldServer,
    model: str | None = None,
    max_turns: int = MAX_TURNS,
    max_tokens: int = MAX_TOKENS,
    cell_timeout_s: float = CELL_TIMEOUT_S,
) -> dict:
    chat = FoundryChat(system=SYSTEM, model=model, max_completion_tokens=MAX_COMPLETION_TOKENS)
    sheet = server.describe()
    prompt = (
        "Here is the brief:\n\n" + sheet["brief"]
        + "\n\nMachine-readable sheet:\n"
        + json.dumps({k: v for k, v in sheet.items() if k != "brief"}, indent=2)
        + "\n\nWrite your first cell. `env` is already in the namespace."
    )

    trace: list[dict] = []
    first_experiment_turn: int | None = None
    first_suspicion_turn: int | None = None
    abort_reason = "submitted"

    with KernelClient(server, cell_timeout_s=cell_timeout_s) as kernel:
        for turn_idx in range(1, max_turns + 1):
            traj_before = len(server.trajectory)
            reply = chat.ask(prompt)
            cell = extract_cell(reply.content)

            if first_suspicion_turn is None and _suspicion_in(reply.content):
                first_suspicion_turn = turn_idx

            rec: dict = {
                "turn": turn_idx,
                "reply_text": reply.content,
                "cell": cell,
                "tokens": {
                    "prompt": reply.prompt_tokens,
                    "completion": reply.completion_tokens,
                    "reasoning": reply.reasoning_tokens,
                },
            }

            if cell is None:
                rec["cell_result"] = {"ok": False, "stdout": "", "error": "no ```python cell in reply"}
                trace.append(rec)
                abort_reason = "no_cell"
                break

            result = kernel.run_cell(cell)
            verbs = [
                {"verb": e.verb, "args": e.args, "cost": e.cost,
                 "budget_remaining": e.budget_remaining, "note": e.note}
                for e in server.trajectory[traj_before:]
            ]
            rec["cell_result"] = {
                "ok": result.ok, "stdout": result.stdout,
                "error": result.error, "truncated": result.truncated,
            }
            rec["verbs"] = verbs
            rec["submit_attempts"] = [v for v in verbs if v["verb"] == "submit"]
            rec["budget_remaining"] = server.budget_remaining
            trace.append(rec)

            if first_experiment_turn is None and any(v["verb"] == "experiment" for v in verbs):
                first_experiment_turn = turn_idx

            if server.terminal:  # an accepted submission ends the episode
                abort_reason = "submitted"
                break

            if chat.usage.total_tokens > max_tokens:
                abort_reason = "max_tokens"
                break
            if turn_idx == max_turns:
                abort_reason = "max_turns"

            fb = (f"Kernel output (ok={result.ok}, budget remaining={server.budget_remaining:.0f}):\n"
                  + (result.stdout or "(no stdout)"))
            if result.error:
                fb += "\nTRACEBACK:\n" + result.error
            fb += "\n\nWrite your next cell (or build and env.submit(code) when ready)."
            prompt = fb

    res = server.result or {}
    return {
        "case_id": getattr(server, "case_id", "dummy_dose_v0"),
        "model": chat.model,
        "accepted": server.terminal,
        "R": res.get("R"),
        "R_unclipped": res.get("R_unclipped"),
        "abort_reason": abort_reason,
        "turns": len(trace),
        "budget_total": server.config.budget,
        "budget_spent": server.config.budget - server.budget_remaining,
        "tokens": {
            "prompt": chat.usage.prompt_tokens,
            "completion": chat.usage.completion_tokens,
            "reasoning": chat.usage.reasoning_tokens,
            "total": chat.usage.total_tokens,
        },
        "signal": {
            "first_experiment_turn": first_experiment_turn,
            "first_suspicion_turn": first_suspicion_turn,
            # heuristic embryo of E1/E2 signatures: did the experiment follow a
            # voiced suspicion (hypothesis->experiment) or precede it?
            "experiment_after_suspicion": (
                None if first_experiment_turn is None or first_suspicion_turn is None
                else first_experiment_turn >= first_suspicion_turn
            ),
        },
        "trace": trace,
    }

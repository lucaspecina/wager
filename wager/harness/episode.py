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

SYSTEM = """You are an investigator building a model of an unknown system through a Python REPL, on a budget.

Each reply has TWO parts, IN THIS ORDER:
1. REASONING (a few sentences of prose): what the latest output told you, how it updates your beliefs about
   how the system actually works (e.g. is an apparent dose->outcome effect causal, or an artefact of who got
   which dose?), what you still need to resolve, and what your next step is and WHY. Think out loud here --
   the investigation lives in this reasoning, not in the code.
2. Exactly ONE Python cell inside a ```python fence: the concrete next step.

The kernel runs the cell and returns its stdout, so PRINT what you want to see; variables persist across
cells. `env` provides:
  env.describe()                      -> dict (free)
  env.observe(source, n)              -> DataFrame (debits cost/row)
  env.experiment(config=..., context=..., n=...) -> DataFrame (debits fixed + cost/row);
        config fixes knobs, e.g. config={"dose": 4.0}; context targets a population, e.g. {"cohort": 1.0}
  env.submit(code_string)             -> result with .accepted and .error
Spend the budget wisely; experiments cost more than observations. When your reasoning has converged, build
your model program (a string defining model(regime, n, seed)) and call env.submit(code). If it fails
validation, read .error, fix, resubmit. For big DataFrames print .head() and .shape, not the whole thing."""

_SUSPICION = (
    "confound", "causal", "spurious", "intervention", "intervene", "stratif",
    "selection bias", "indication", "backdoor", "back-door", "collider",
    "do(dose", "do-operator", "not causal", "reverse caus",
)

# v0.1 BEHAVIORAL signature (Decision Log v0.16): attribution analysis is what the
# CODE does, not what the prose says (the lexical detector gave None in 4/5). These
# are conditioning/attribution operations on data: stratification or regression.
_ATTRIBUTION_OPS = (
    "groupby", "qcut", ".cut(", "pd.cut", ".corr(", "corrcoef", "np.cov",
    "polyfit", "lstsq", "ols(", "smf.", "stratif", "residual", "partial",
)


def _suspicion_in(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _SUSPICION)


def _has_attribution(code: str) -> bool:
    low = code.lower()
    return any(op in low for op in _ATTRIBUTION_OPS)


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
        + "\n\nReason briefly about your opening plan, then write your first cell. "
        "`env` is already in the namespace."
    )

    trace: list[dict] = []
    first_experiment_turn: int | None = None
    first_suspicion_turn: int | None = None
    first_attribution_turn: int | None = None
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

            if cell is not None and first_attribution_turn is None and _has_attribution(cell):
                first_attribution_turn = turn_idx

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
            fb += ("\n\nReason about what this result tells you (does it confirm or refute your current "
                   "hypothesis? what does it imply for the next step?), then write your next cell "
                   "(or build and env.submit(code) when your reasoning has converged).")
            prompt = fb

    res = server.result or {}
    return {
        "case_id": getattr(server, "case_id", "dummy_dose_v0"),
        "model": chat.model,
        "accepted": server.terminal,
        "R": res.get("R"),
        "R_unclipped": res.get("R_unclipped"),
        "submission_code": res.get("code"),  # the accepted submission, for post-hoc diagnostics
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
            # v0.1 BEHAVIORAL (Decision Log v0.16): did attribution analysis
            # (stratification/regression on data) happen BEFORE paying for the
            # first experiment? -- hypothesis-before-spend, read from the CODE.
            "first_experiment_turn": first_experiment_turn,
            "first_attribution_turn": first_attribution_turn,
            "attribution_before_experiment": (
                first_attribution_turn is not None
                and (first_experiment_turn is None or first_attribution_turn <= first_experiment_turn)
            ),
            # v0 LEXICAL (kept for comparison; known weak -- gave None in 4/5):
            "first_suspicion_turn_lexical": first_suspicion_turn,
        },
        "trace": trace,
    }

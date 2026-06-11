"""C1 — LLM SMOKE (Decision Log v0.14: integration-first).

The thinnest real path: gpt-5.4 (Foundry) gets the dummy brief + contract, writes
a Python cell, the kernel runs it, the model sees stdout and writes another. A few
round-trips. Validates the multi-turn plumbing, contract comprehension and kernel
ergonomics BEFORE the full harness exists. If anything Responses-API-class breaks,
it breaks here.

NOT an eval. Saves a per-turn JSON trace (the embryo of the E1/E2 signature
format). Run:  .venv/Scripts/python cases/dummy_dose_v0/c1_smoke.py
"""

import json
from pathlib import Path

from wager.agent.cells import extract_cell
from wager.agent.llm_client import FoundryChat
from wager.factory.case_loader import load_meta, load_world_sample
from wager.harness.c1_env import C1Env
from wager.harness.kernel import Kernel

CASE_DIR = Path(__file__).parent
N_TURNS = 3
BUDGET = 5000.0

SYSTEM = """You are an investigator modelling an unknown system through a Python REPL.
You will be given a brief. Work the problem by writing ONE Python cell per reply,
always inside a ```python fenced block. The kernel runs it and returns stdout, so
PRINT anything you want to see. Variables persist across cells. Be concise: in each
cell, take one concrete step (inspect data, compute a statistic, test an idea).
Do not write prose outside the code fence beyond a one-line plan."""


def build_first_prompt(env: C1Env) -> str:
    sheet = env.describe()
    return (
        "Here is the brief:\n\n"
        + sheet["brief"]
        + f"\n\nMachine-readable sheet:\n{json.dumps({k: v for k, v in sheet.items() if k != 'brief'}, indent=2)}"
        + "\n\nWrite your first cell. `env` is already in the namespace."
    )


def main() -> None:
    meta = load_meta(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    brief = (CASE_DIR / "brief.md").read_text(encoding="utf-8")
    env = C1Env(
        world_sample=world_sample,
        brief=brief,
        schema=meta.column_names,
        sources={"registros_clinicos_2019_2023": 1.0},
        budget=BUDGET,
    )
    kernel = Kernel(injected={"env": env})
    chat = FoundryChat(system=SYSTEM, max_completion_tokens=6000)

    trace: list[dict] = []
    prompt = build_first_prompt(env)
    for turn_idx in range(1, N_TURNS + 1):
        reply = chat.ask(prompt)
        cell = extract_cell(reply.content)
        print(f"\n===== TURN {turn_idx} | model reply ({reply.completion_tokens} compl. tok) =====")
        print(reply.content)
        record = {
            "turn": turn_idx,
            "reply_text": reply.content,
            "cell": cell,
            "prompt_tokens": reply.prompt_tokens,
            "completion_tokens": reply.completion_tokens,
            "reasoning_tokens": reply.reasoning_tokens,
            "latency_s": round(reply.latency_s, 2),
        }
        if cell is None:
            record["cell_result"] = {"ok": False, "stdout": "", "error": "no ```python cell found"}
            print("  [harness] no cell found in reply; stopping")
            trace.append(record)
            break
        result = kernel.run(cell)
        record["cell_result"] = {"ok": result.ok, "stdout": result.stdout, "error": result.error}
        record["budget_remaining"] = env.budget_remaining
        trace.append(record)
        print(f"----- kernel output (ok={result.ok}, budget_left={env.budget_remaining:.0f}) -----")
        print(result.stdout if result.stdout else "(no stdout)")
        if result.error:
            print("ERROR:\n" + result.error)
        # feed the output back as the next user turn
        fb = f"Kernel output (ok={result.ok}, budget remaining={env.budget_remaining:.0f}):\n"
        fb += (result.stdout or "(no stdout)")
        if result.error:
            fb += "\nTRACEBACK:\n" + result.error
        fb += "\n\nWrite your next cell."
        prompt = fb

    out_dir = CASE_DIR / "traces"
    out_dir.mkdir(exist_ok=True)
    trace_path = out_dir / "c1_smoke_trace.json"
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"C1 SMOKE done: {len(trace)} turns, model={chat.model}")
    print(f"  tokens: prompt={chat.usage.prompt_tokens} completion={chat.usage.completion_tokens} "
          f"reasoning={chat.usage.reasoning_tokens} total={chat.usage.total_tokens} "
          f"({chat.usage.calls} calls)")
    cells_ok = sum(1 for r in trace if r.get("cell_result", {}).get("ok"))
    print(f"  cells run ok: {cells_ok}/{len(trace)}")
    print(f"  trace -> {trace_path}")


if __name__ == "__main__":
    main()

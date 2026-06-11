# Brief - clinic dose policy

You are advising a clinic that must set its **dose policy** for incoming patient
populations, including doses and populations outside the historical record.
Getting the dose-response relationship wrong -- especially where it flattens out
(saturates) -- is costly. Your job is to build a model of how this system behaves,
good enough to predict outcomes under dose settings the clinic has not tried yet.

## Technical sheet

Observables -- every dataset, and your delivered model, use exactly these columns:

| column  | type  | unit | meaning                            |
|---------|-------|------|------------------------------------|
| dose    | float | mg   | administered dose                  |
| marker  | float | a.u. | a measured clinical marker (noisy) |
| outcome | float | a.u. | recovery score (higher is better)  |

Sources you can query (each debits budget):

- `registros_clinicos_2019_2023` -- routine observational records: one row per past
  case, with its administered dose and measured outcome. Cost: 1 unit per row.

Control surface (what an experiment can set):

- `dose` -- settable in [0, 10] mg.
- `cohort` -- a population baseline level; a property of who arrives, which an
  experiment can target (e.g. `context={"cohort": 1.0}`), not something you set
  per patient. The observational source is `cohort = 0`.

Budget: abstract units, shown by `env.describe()`. `describe` is free; `observe`
and `experiment` debit.

## Interaction

You write Python cells. A persistent kernel runs them; variables persist across
cells. **Print whatever you want to see** -- only stdout is returned to you
(for big DataFrames, print `.head()` and `.shape`). `env` provides:

- `env.describe()` -- free; returns this sheet as a dict.
- `env.observe(source, n)` -- DataFrame of `n` observational rows; debits cost/row.
- `env.experiment(config=..., context=..., n=...)` -- runs a fresh trial under a
  dose/population you choose and returns a DataFrame; debits a fixed cost + cost/row.
  Example: `env.experiment(config={"dose": 6.0}, context={"cohort": 0.0}, n=400)`.
- `env.submit(code)` -- deliver your model (see below); returns a result with
  `.accepted` and `.error`.

`numpy`, `pandas`, `scipy`, `sklearn` are importable. No network, no file access.

## Delivery contract

Deliver a Python program (as a string) defining

    def model(regime, n, seed) -> pandas.DataFrame   # columns exactly: dose, marker, outcome

`regime` always has `.config` (a dict, possibly empty), `.context` (a dict,
possibly empty) and `.horizon` -- use them directly, no defensive checks needed.
`regime.config` may fix `dose` (e.g. `{"dose": 4.0}`) -- then your model must
generate outcomes for that fixed dose -- or be empty (generate the natural
observational population). `regime.context` may carry `{"cohort": <level>}`.
`regime.horizon` is unused here. The program may import numpy/pandas/scipy/sklearn,
runs in a sandbox with a per-call time limit, and may also be an ensemble
`[(weight, code), ...]` to express uncertainty across rival models.

Call `env.submit(code)` when ready. A quick validation checks the columns, types
and row count on a few public settings and returns an actionable error if
something is off (the episode stays open so you can fix and resubmit). Your model
is then scored by comparing its output against the real system under **undisclosed
dose settings and populations**, weighted toward the dose-policy decisions above.

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

Budget: abstract units, shown by `env.describe()`. `describe` is free; `observe`
debits.

## Interaction

You write Python cells. A persistent kernel runs them; variables persist across
cells. **Print whatever you want to see** -- only stdout is returned to you. An
object `env` is available:

- `env.describe()` -- free; returns this sheet as a dict (schema, sources, budget).
- `env.observe(source, n)` -- returns a pandas DataFrame of `n` rows; debits cost.

`numpy`, `pandas`, `scipy`, `sklearn` are importable. No network, no file access.

## Delivery contract (for later)

When ready you will deliver a Python program defining

    def model(regime, n, seed) -> pandas.DataFrame   # columns exactly: dose, marker, outcome

where `regime.config` may fix `dose` (e.g. `{"dose": 4.0}`) -- then your model must
generate outcomes for that fixed dose -- or be empty (generate the natural
observational population). You will be scored by comparing your model's output
against the real system under **undisclosed dose settings**, weighted toward the
dose-policy decisions above.

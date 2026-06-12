# Dosing policy for incoming cohorts

You advise a clinic that must set a single drug **dose** (0-10 mg) for the
patients who arrive. Your job is to hand back a model that predicts the
distribution of the recovery **outcome** under any dose you choose to set, so the
clinic can price its policy.

## What is at stake

A poor outcome -- a recovery score below the harm line of -5 -- is far costlier than a forgone gain: harming a patient with the wrong dose is the failure the clinic most wants to avoid. So predicting *where the bad tail sits* under a given dose matters as much as predicting the average.

The clinic also warns you: **the cohorts that arrive are not the cohort in your
records.** The historical data was collected from one standing population; the
patients you must dose for may be composed quite differently, and the operator
needs a model that still holds when the population shifts. Patient-to-patient
heterogeneity in how people respond is plausible and worth investigating.

## What you can do

- `observe(records)` -- cheap historical clinic records. Columns: `dose`,
  `outcome`. (The records do **not** include any assay beyond dose and outcome.)
- `buy_instrument(assay)` -- pay to run a per-patient **biomarker** assay that
  adds a `marker` column to what you can see. It is noisy.
- `experiment(design)` -- pay to set the dose on a sample and measure outcomes
  (randomization breaks the historical assignment, not the measurement channel).
- `submit(model)` -- hand back `model(regime, n, seed) -> table` over
  `dose, marker, outcome`.

## The catch you are paid to find

The historical dose-outcome association is what an untrained eye would price. The
clinic suspects it is misleading and is paying you to find out *why*, *for whom*,
and *what actually happens to the outcome -- and its harmful tail -- when the dose
is set deliberately for a population unlike the one on record.*

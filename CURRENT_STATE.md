# CURRENT_STATE — WAGER

> Estado vivo del repo: qué corre hoy, qué falta. Lo mantiene Claude Code al día en cada
> sesión de trabajo (regla: NORTH_STAR §0.10). Última actualización: **2026-06-11**.

## Qué corre hoy

**Slice 1 completo y verde**: el reward path end-to-end sobre el mundo dummy
`dummy_dose_v0`, con L0/L1/L2 cumpliendo sus criterios de aceptación.

- `pip install -e .[dev]` + `pytest` → **45 tests verdes** (Python 3.13).
- `wager/contracts/` — contratos Pydantic v2 (world, case, reports).
- `wager/reward/` — **zona cero-LLM** (allowlist de imports en CI): `seeds`,
  `distance` (energy distance + estandarización por la verdad), `mdl`
  (AST-min→zlib + ensembles por concat canónico), `sandbox` (AST-lint + proceso
  hijo + red off + timeout), `scorer` (R, D_MAX), `ladder` (L1), `variance` (L2).
- `wager/factory/` — `case_loader`, `world_lint` (lado fábrica; LLM permitido acá).
- `cases/dummy_dose_v0/` — `world.py` (SCM: confounding-by-indication mecanístico
  + dosis-respuesta saturante), `battery.json` (16 ítems a mano), `meta.json`,
  `ladder/` (6 fixtures determinísticos commiteados), `make_ladder_fixtures.py`
  (regenera fixtures + calibra λ), `run_slice.py` (entregables), `diagnose.py`.

### Entregables medidos (`python cases/dummy_dose_v0/run_slice.py`)

- **L1**: orden total de las 6 verdades degradadas con todos los márgenes ≥5%.
  R = {verdad 1.000, perturbado 0.941, linealizado 0.725, gemelo 0.340,
  ingenuo 0.000, nulo 0/−2.55}. Margen más ajustado: verdad→perturbado 5.9%.
- **L2**: CV(R) = 1.1% sobre 20 seed-sets (objetivo <5%); CV(S_verdad) = 0.4%;
  descomposición std(R) total 0.0079 = lado-mundo 0.0076 ⊕ lado-maqueta 0.0021.
- **Costo K×n×m** (16×1000×5): L1 8.5s, L2 57.6s.

## Hallazgos del Slice 1 (Decision Log v0.12)

La escalera L1 destapó tres bugs de **maquinaria** (no de fixtures) al fallar el
orden total; se diagnosticó per-ítem (`diagnose.py`) antes de tocar nada:
1. D_MAX clampeaba toda distancia (debía asignarse solo en crash).
2. D_MAX referenciaba el null equivocado (permutación de la verdad, no el null model).
3. Los márgenes L1 se medían contra S_verdad−S_nulo (un outlier patológico);
   ahora contra el rango de normalización S_verdad−S_ingenuo (unidades de R).
Fixtures de la escalera intactos.

## Qué falta (orden de la escalera, NORTH_STAR §6)

1. Harness interactivo (REPL + env handle opaco RPC, ARCHITECTURE §8/§14.2) +
   endurecimiento real del sandbox (los gaps están en `REDTEAM.md`).
2. Derivación automática de rivales (§5) y batería (§6) — al existir, **expira la
   excepción de bootstrap** (batería y escalera a mano del Slice 1).
3. E1: ~20 mundos a mano en 2 familias, ≥5 suites, certificados (§7), frontiers
   vía API (ARCHITECTURE §12).

## Deuda / pendientes

- Sandbox v0 es honesto pero no es jaula real: gaps declarados en `REDTEAM.md`
  (C-extensions, rlimit de memoria, fork). Se cierran con el harness interactivo.
- λ es **provisional** (calibrado al 5% del rango de normalización del dummy);
  se recalibra sobre la suite E1.
- Issue conocido E2 (diferido): clip(R,0,1) y sparsity de gradiente; rotación de
  seed-sets durante entrenamiento.
- Ensembles `[(peso, code)]`: `mdl_bytes` ya los soporta; el scoring de mezcla
  muestreada falta (no hay fixtures de ensemble en el Slice 1).

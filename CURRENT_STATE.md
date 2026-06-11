# CURRENT_STATE — WAGER

> Estado vivo del repo: qué corre hoy, qué falta. Lo mantiene Claude Code al día en cada
> sesión de trabajo (regla: NORTH_STAR §0.10). Última actualización: **2026-06-11**.

## Qué corre hoy

**Slice 1 (reward path) y Slice 2 (harness interactivo, C1+C2+C3) completos y verdes.**
`pip install -e .[dev,agent]` + `pytest` → **69 verdes, 1 skip** (test LLM opt-in;
correr con `RUN_LLM_TESTS=1`). Python 3.13.

- `wager/contracts/` — contratos Pydantic v2 (world, case, episode, reports).
- `wager/reward/` — **zona cero-LLM** (allowlist de imports en CI + no importa
  `wager.agent`/`wager.harness`): `seeds`, `distance`, `mdl`, `sandbox`, `scorer`
  (R, D_MAX), `ladder` (L1), `variance` (L2), `episode_score` (R de submission).
- `wager/factory/` — `case_loader`, `world_lint` (lado fábrica; LLM permitido acá).
- `wager/agent/` — **lado solver (LLM)**: `llm_client` (Foundry v1 multi-turn),
  `cells`. Nunca importado por `wager.reward`.
- `wager/harness/` — `world_server` (autoridad del episodio: verbos + ledger +
  humo + scoring), `kernel_proc` (kernel en proceso separado + env proxy data-only),
  `episode` (loop LLM + guardas + trace), `env`/`case_episode`, `kernel`/`c1_env` (C1).
- `cases/dummy_dose_v0/` — `world.py`, `battery.json`, `meta.json` (+ episode),
  `ladder/`, `brief.md` (cara pública, ASCII), `solvers.py`, runners
  (`run_slice`, `c1_smoke`, `c2_pair`, `e0_episode`, `e05_episodes`,
  `make_ladder_fixtures`, `ablate_m`, `diagnose`), `traces/` (E0/E0.5).

### Entregables medidos (`python cases/dummy_dose_v0/run_slice.py`, defaults v0 K=16 n=1000 m=2)

- **L1**: orden total de las 6 verdades degradadas con todos los márgenes ≥5%,
  cada peldaño anotado como ancla (R fijo) o medición. R = {verdad 1.000
  (anchor:S_truth), perturbado 0.942, linealizado 0.728, gemelo 0.344, ingenuo
  0.000 (anchor:S_naive), nulo 0/−2.53 (reference:S_null)}. Margen más ajustado:
  verdad→perturbado 5.85%.
- **L2**: CV(R) = 1.17% sobre 20 seed-sets (objetivo <5%); CV(S_verdad) = 0.54%;
  descomposición std(R) total 0.0084 = lado-mundo 0.0075 ⊕ lado-maqueta 0.0039.
- **Costo K×n×m** (16×1000×2): L1 6.4s, L2 27.1s.
- **Ablación de m** (`ablate_m.py`): CV(R) 1.17/1.13/1.10% para m=2/3/5 → m=2
  default v0 (el lado-mundo domina; subir m casi no mueve el total).

## Hallazgos del Slice 1 (Decision Log v0.12)

La escalera L1 destapó tres bugs de **maquinaria** (no de fixtures) al fallar el
orden total; se diagnosticó per-ítem (`diagnose.py`) antes de tocar nada:
1. D_MAX clampeaba toda distancia (debía asignarse solo en crash).
2. D_MAX referenciaba el null equivocado (permutación de la verdad, no el null model).
3. Los márgenes L1 se medían contra S_verdad−S_nulo (un outlier patológico);
   ahora contra el rango de normalización S_verdad−S_ingenuo (unidades de R).
Fixtures de la escalera intactos.

## Resultados del Slice 2 (C2 + C3, Decision Log v0.15)

- **C2**: naive R=0.044 vs canonical R=1.000 por el juego real (investigar gana).
- **E0** (gpt-5.4): R=0.895, 4 turnos, 17.6k tokens — jugable; inventó un latente.
- **E0.5**: gpt-5.4 R∈{0.887,0.958}; DeepSeek-V3.2 R=0.000 (regresó sin latente →
  brecha de teoría visible). Cross-family pagó.
- Fricciones resueltas: no-ASCII en briefs; `hasattr` faltaba en el sandbox.

## Qué falta

1. Derivación automática de rivales (§5) y batería (§6) — al existir, **expira la
   excepción de bootstrap** (batería, escalera L1 y brief a mano).
2. E1: ~20 mundos a mano en 2 familias, ≥5 suites, certificados (§7) (ARCHITECTURE §12).
3. Hardening del handle opaco (jaula de filesystem, gc/closure) — gaps en `REDTEAM.md`.
4. Mejor extractor de firmas del trace (el keyword-suspicion v0 sub-detecta).

## Deuda / pendientes

- Sandbox v0 es honesto pero no es jaula real: gaps declarados en `REDTEAM.md`
  (C-extensions, rlimit de memoria, fork). Se cierran con el harness interactivo.
- λ es **provisional** (calibrado al 5% del rango de normalización del dummy);
  se recalibra sobre la suite E1.
- Issue conocido E2 (diferido): clip(R,0,1) y sparsity de gradiente; rotación de
  seed-sets durante entrenamiento.
- Ensembles `[(peso, code)]`: `mdl_bytes` ya los soporta; el scoring de mezcla
  muestreada falta (no hay fixtures de ensemble en el Slice 1).

# CURRENT_STATE — WAGER

> Estado vivo del repo: qué corre hoy, qué falta. Lo mantiene Claude Code al día en cada
> sesión de trabajo (regla: NORTH_STAR §0.10). Última actualización: **2026-06-11**.

## Qué corre hoy

- Scaffolding del paquete: `pip install -e .[dev]` + `pytest` (solo tests de wiring del esqueleto).
- Sin reward path todavía: ningún mundo, scorer ni batería implementados.

## En curso

- **Slice 1** (reward path end-to-end con mundo dummy): plan propuesto a Lucas, **esperando aprobación** antes de codear (protocolo en CLAUDE.md → Workflow).

## Qué falta (orden de la escalera, NORTH_STAR §6)

1. Slice 1: contenedor de caso + scorer + L1 (escalera, orden total en el dummy canónico) + L2 (CV < 5% sobre R, costo K×n×m) + CI cero-LLM (estático + dinámico) + tests de contrato + sandbox red-team.
2. Harness interactivo (REPL + env handle opaco, ARCHITECTURE §8).
3. Derivación automática de rivales (§5) y batería (§6) — al existir, **expira la excepción de bootstrap** (Decision Log v0.10).
4. E1: ~20 mundos a mano en 2 familias, ≥5 suites, certificados computados, frontiers vía API (ARCHITECTURE §12).

## Decisiones recientes que condicionan el código

- **Decision Log v0.10** (NORTH_STAR §11): frontera temporal del cero-LLM, semántica de seeds (lado-mundo fijo en `battery.json`, lado-maqueta `derive_seed(seed, j)`), anclas con función de score completa + serialización canónica del rival (a), L1 monotonía-por-eje en producción (orden total solo dummy), L2 sobre B seed-sets re-sampleados, MDL = zlib(AST minificado) con ensembles por concat canónico, D_MAX_item = 1.5 × D(verdad, nulo), rivales (a)/(d) sobre pool observacional completo.

## Deuda / pendientes operativos

- Ninguna deuda de código (no hay código).
- Issue conocido E2 (diferido): clip(R,0,1) y sparsity de gradiente; rotación de seed-sets durante entrenamiento.

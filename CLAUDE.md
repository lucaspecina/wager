# CLAUDE.md — WAGER

Operativa del repo para Claude Code. Leer en este orden la primera vez:

1. `NORTH_STAR.md` — la constitución: por qué existe el proyecto, ethos, diseño conceptual, programa experimental, red-team. **§0 contiene las reglas de mantenimiento de los docs: cumplirlas siempre.**
2. `ARCHITECTURE.md` — el diseño técnico: contratos, librería de operadores, semántica de rivales, algoritmo de batería, harness, scoring.
3. Este archivo — convenciones operativas.

## Jerarquía de autoridad

`NORTH_STAR §2 (Ethos)` > `NORTH_STAR (diseño)` > `ARCHITECTURE` > issues > código.
El código nunca contradice los docs en silencio: si la implementación revela un error de diseño, se propone la edición del doc + entrada en el Decision Log de NORTH_STAR.

## Reglas duras (resumen de bolsillo — el detalle está en NORTH_STAR)

- **JAMÁS un LLM en el cómputo del reward.** Si una solución lo requiere, frenar y discutir. (NORTH_STAR §2.2)
- Esa regla se convierte en código desde el día uno: **test de CI que falla el build si hay llamadas a LLM en el camino del reward** (ARCHITECTURE §13-L0). Ídem sandbox red-team: tests que intentan hacer trampa y deben fallar.
- **Integración LLM primero** (Decision Log v0.14): todo subsistema con superficie hacia un LLM (harness/solver; en el futuro brief writer, prior evocado, digestion, validators) tiene como **PRIMER milestone un smoke test con LLM real del camino más fino** — nunca como último. Los bugs de integración (plumbing multi-turn, comprensión del contrato, ergonomía del sandbox, costos reales) son los que más calendario queman y solo aparecen con modelo real. Los tests de wiring y los solvers scripteados siguen como controles, pero **no gatean la primera llamada real**. Excepción que no se mueve con el apuro: el reward path sigue cero-LLM (el CI lo protege; ataque #18).
- Todo mundo nuevo pasa la **escalera de verdades degradadas** (ARCHITECTURE §13-L1) antes de entrar a una suite.
- Antes de tocar submission/batería/score: releer NORTH_STAR §4.4 y ARCHITECTURE §5–6–9.
- Las conductas del agente se **observan** (traces, firmas), nunca se premian. (NORTH_STAR §2.1, §2.6)
- Rivales y batería se **derivan** del caso declarado en `meta.json`; nunca se autorean a mano por caso.
- La librería de operadores **crece a demanda de semillas reales** (moraleja de un caso real que no se puede expresar → proponer operador nuevo), nunca por imaginación suelta. El solver jamás ve la taxonomía de operadores.
- Casos con semilla investigativa: **test de contaminación obligatorio** antes de certificar (ARCHITECTURE §4); trasplante cruzado de dominio por defecto para semillas famosas. Las tres fuentes de generación (semillas / composición / búsqueda) tienen roles distintos y ninguna reemplaza a las otras.
- Todo mundo nuevo debe pasar sus **certificados** (ARCHITECTURE §7), incluida carga diferencial ≥2 coordenadas.
- El handle del mundo es **opaco server-side**: el agente jamás puede leer `world.py`, `battery.json` ni `rivals/`.
- El brief lo escribe un proceso **ciego** a batería y rivales (anti-leak).

## Workflow

- Unidad de avance: el **slice vertical más chico** que ejercite el reward path completo (mundo → episodio → submission → score).
- El orden de trabajo lo define la escalera experimental (NORTH_STAR §6). **E1 primero**: no requiere RL ni designer automático. Lo mínimo para E1 está en ARCHITECTURE §12.
- Primer slice sugerido: contenedor de caso + scorer con UN mundo dummy hardcodeado y una batería escrita a mano — smoke test end-to-end del reward path. Recién después, harness interactivo. (Batería y peldaños L1 a mano = **excepción de bootstrap, SOLO Slice 1**; expira cuando exista la derivación automática de rivales §5 + batería §6 — Decision Log v0.10.)
- Tests de wiring por componente; tests E2E con LLM real solo cuando el wiring está verde.
- Toda decisión de diseño no trivial → Decision Log de NORTH_STAR (fecha — decisión — razón en una línea).
- Open questions nuevas → NORTH_STAR §10 (inbox); al resolverse, migran al Decision Log.
- **Checklist de supersesión (regla dura, Decision Log v0.30)**: toda entrada del Decision Log que **supersede** una decisión previa DEBE hacer **grep de la regla vieja en TODOS los docs** y enumerar + tildar cada ubicación que la edita. Principio **"una regla, una casa"**: la regla vive en UNA sección; el resto referencia. (Origen: la v0.29 editó ARCHITECTURE §7 pero olvidó §5, que quedó contradiciendo en silencio — lo destapó una auditoría código-vs-docs.)
- **Auditoría código-vs-docs por iniciativa propia**: ante una inconsistencia doc-doc o doc-código, **reportar con ubicación exacta + fix propuesto, nunca arreglar en silencio**; aplicar recién con aprobación (NORTH_STAR §0.1: el código nunca contradice los docs en silencio).

## Referencia SREG — política de cuarentena

El repo SREG (proyecto anterior, mismo autor) es **referencia de SOLO LECTURA** en: `C:\Users\YT40432\Desktop\lp\research\lucaspecina\synthetic-research-envs`.

- **Regla spec-first**: SREG se consulta SOLO cuando el spec WAGER del componente ya está escrito y aceptado. SREG responde "cómo implemento este spec", nunca "qué debería ser el spec".
- **Allowlist** (portear con mínima cirugía — plomería neutral que costó días de debugging): kernel Jupyter persistente (patrón python_exec), cliente LLM Azure incluidos los fixes de multi-turn de la Responses API, patrones de contratos Pydantic, maquinaria anti-leak (capsule / writers ciegos), scaffolding de repo y tests.
- **Cirugía obligatoria** (leer el patrón, reescribir contratos y prompts contra el spec WAGER): digestion agent, architect + lints, validators — embeben supuestos de v1.5.
- **Denylist** (NO leer — es la filosofía que matamos y leerla invita a recontrabandearla): evaluator/judge, restos del compiler NL↔IR, scoring por rubrics/SQ, formatos de claims.

**Portear deliberadamente, nunca importar por arrastre.** La lección fundante (por qué murió el compiler) está en NORTH_STAR §2.3.

## Convenciones

- Python 3.11, Pydantic para contratos, pytest, dependencias mínimas (numpy/pandas/scipy; nada exótico sin justificar).
- Docs en español, código e identificadores en inglés.
- Los nombres de suites de mundos siguen la convención de científicos arquetipo: Kepler (observacional), Snow (anomalías), Mendel (constructos latentes), Semmelweis (prior vs evidencia).
- Casos en `cases/<case_id>/` con la anatomía exacta de ARCHITECTURE §1.

## Infraestructura

- **GPU**: VM Azure `lp-gpu-h100-x2-spot` (Standard NC80adis H100 v5: 2× H100 94GB, 80 vCPU, 640 GiB RAM). Es **SPOT** → preemptible: checkpointing y reanudación obligatorios en todo job largo, desde el día uno.
- **Qué corre dónde**: **E1 es API-bound** (modelos frontier vía API; scoring, oráculos y rivales son CPU) — la GPU es opcional en E1 (servir modelos abiertos para engordar el spread). La GPU es central en **E2**: RL de una policy abierta de ~4–8B (group rollouts con seeds de batería compartidos para baselines de baja varianza; LoRA o full según memoria) + reference solvers locales.
- **Costos**: estimar el presupuesto de API de E1 ANTES de correr (orden: ~10³ episodios de REPL largo); diseñar la primera pasada como la mínima informativa.
- **Workflow y conexiones**: usar las **skills de usuario** de Lucas (workflow Azure/VM, SSH, convenciones) — no duplicar esa información acá.

## Estado actual

El estado vivo (qué corre hoy, qué falta, próximo paso) está en `CURRENT_STATE.md` — mantenerlo SIEMPRE actualizado al cerrar cada sesión de trabajo. Decision Log en v0.30 (NORTH_STAR); ARCHITECTURE con §9.3 (score combinado) + §7 ((d-obs)/(d-exp) + certificado de visibilidad). Último: score combinado implementado (paso 1); ronda v0.30 de auditoría doc-código (certificados auto-descriptivos). **Próximo paso: (2) calibrar `c_F` mínimo-suficiente.**

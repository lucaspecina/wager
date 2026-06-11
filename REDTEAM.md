# REDTEAM.md — archivo vivo de escapes del sandbox

> Cada idea nueva de trampa se convierte en un test (Decision Log v0.11). Este
> archivo es la lista; los tests viven en `tests/test_sandbox_redteam.py`.
>
> **Threat model del Slice 1**: las submissions son fixtures NUESTROS. El
> sandbox v0 (AST-lint + proceso hijo con builtins restringidos + red
> deshabilitada + cwd aislado + timeout) debe frenar lo accidental y lo obvio,
> y todo escape debe **fallar cerrado** (SandboxError → cap en D_MAX), nunca
> devolver un valor ni filtrar. El endurecimiento real (RPC / jaula de
> filesystem) llega con el harness interactivo (ARCHITECTURE §14.2). La red
> está deshabilitada en scoring de PRODUCCIÓN siempre, no solo en CI.

## Invariante de aceptación

Todo escape de la lista: rechazado en lint/init, o `SandboxError` en runtime.
Nunca un retorno exitoso, nunca lectura de `world.py` / `battery.json` / red.

## Escapes cubiertos (→ test)

| # | Escape | Vector | Defensa | Estado |
|---|--------|--------|---------|--------|
| 1 | `read_world_py` | `open('world.py')` | cwd aislado + `open` fuera de builtins | test ✓ |
| 2 | `read_battery_json` | `open('../battery.json')` | ídem | test ✓ |
| 3 | `subprocess` | `import subprocess` | import no en allowlist (lint) | test ✓ |
| 4 | `os_system` | `import os; os.system` | `os` no en allowlist de submission | test ✓ |
| 5 | `network_socket` | `import socket` | no en allowlist + socket parcheado | test ✓ |
| 6 | `eval_builtin` | `eval(...)` | `eval` fuera de builtins + nombre prohibido | test ✓ |
| 7 | `exec_builtin` | `exec(...)` | ídem | test ✓ |
| 8 | `dunder_globals` | `model.__globals__` | acceso a dunder bloqueado (lint) | test ✓ |
| 9 | `import_via_dunder` | `().__class__.__bases__` | acceso a dunder bloqueado (lint) | test ✓ |
| 10 | `open_write` | `open('x','w')` | `open` fuera de builtins | test ✓ |
| 11 | `relative_import` | `from . import secrets` | imports relativos prohibidos (lint) | test ✓ |
| 12 | `timeout` (DoS) | `while True: pass` | timeout por llamada → kill | test ✓ |
| 13 | columnas equivocadas | DataFrame mal formado | validación parent-side | test ✓ |
| 14 | NaN/inf en salida | valores no finitos | validación parent-side | test ✓ |
| 15 | crash arbitrario | `raise` | cap en D_MAX por ítem (1.5× null) | test ✓ |

## Kernel opaco del episodio (C3 — `tests/test_opaque_kernel.py`)

Threat model: el agente (LLM) escribe celdas que corren en un **proceso separado**;
el mundo (WorldServer, `world.py`, batería) vive en el proceso principal. El agente
solo lo alcanza por verbos que cruzan **datos** (dicts/DataFrames), nunca objetos
ni callables. Invariante: todo intento de alcanzar el mundo por fuera de los verbos
**falla cerrado**.

| # | Escape | Vector | Defensa | Estado |
|---|--------|--------|---------|--------|
| 16 | introspección de `env` | `env.__dict__`, `dir(env)` | el pipe vive en un closure, no en un atributo → `__dict__` vacío | test ✓ |
| 17 | leer `world.py`/`battery.json` | `open('world.py')` etc. | cwd del subproceso aislado (mkdtemp) → no resuelve | test ✓ |
| 18 | callable en `design` | `experiment(config={'dose': lambda…})` | el proxy fuerza `json.dumps` de los args → falla cerrado | test ✓ |
| 19 | valor no-data en `design` | `experiment(config={'dose':'huge'})` | validación server-side `ExperimentDesign` (extra=forbid, float) → error como dato | test ✓ |
| 20 | overspend vía proxy | `observe` masivo | ledger server-side → `BudgetError` como dato | test ✓ |
| 21 | encoding (no-ASCII) | texto unicode por el subproceso | round-trip utf-8 verificado (em-dash/bullet/accent/arrow) | test ✓ |

## Gaps conocidos del kernel opaco (NO cubiertos en v0 — declarados)

- **Lectura por path absoluto**: el cwd aislado frena reads relativos, pero un path
  absoluto conocido NO está bloqueado (el agente no conoce el path; mitigación débil).
- **Alcanzar el pipe por gc/closure**: `gc.get_referents` sobre el closure de los
  métodos de `env` podría llegar a la `Connection`. Aun así, el peor caso es
  re-emitir verbos (budget-limitado, sin info extra); los artefactos secretos están
  en OTRO proceso, no en el del agente. Endurecimiento real (jaula de filesystem +
  seccomp + auth del canal) → harness RPC completo (ARCHITECTURE §14.2).

## Integridad del instrumento (no es escape, es equidad — Decision Log v0.16)

Un crash silencioso es indistinguible de "honestamente malo": una submission que
crashea en la batería cae a D_MAX en cada ítem → R=0, sin señal de la causa. Si la
causa es una elección legítima del modelo (p.ej. la API legacy `np.random.seed`,
que rechaza seeds ≥ 2³²), el instrumento penaliza el RNG, no el juicio (primo del
ataque #17). Defensas: (a) `derive_seed` en [0, 2³²-1] (agnóstico a la API de RNG);
(b) smoke con regímenes diversos + seeds representativos para cazar el crash en el
submit con error accionable, no en silencio; (c) **detector**: el breakdown per-ítem
(`diagnose_submission.py`) distingue D_MAX-por-crash de distancias honestas — uso
obligatorio antes de concluir nada sobre un R=0/clipeado.

## Gaps conocidos del sandbox de scoring (NO cubiertos en v0 — declarados)

- **Builtins por C-extension**: numpy/scipy se pre-importan con builtins
  completos antes del lockdown; un atacante motivado podría buscar gadgets ahí.
  Mitigación real: proceso/contenedor con seccomp en el harness interactivo.
- **Agotamiento de memoria**: el timeout corta CPU, no RSS. Falta rlimit.
- **Fork/spawn desde el worker**: `multiprocessing` no está en el allowlist de
  submission, pero no hay un guard de `os.fork` a nivel kernel.
- **Side-channels de tiempo**: fuera de scope (no hay secreto que extraer en el
  número del reward; la batería y rivales son server-side).

## Cómo agregar un escape

1. Pensaste un vector nuevo → agregá la fila acá.
2. Agregá el caso a `ESCAPES` (o un test dedicado) en
   `tests/test_sandbox_redteam.py`, afirmando que falla cerrado.
3. Si pasa (= el sandbox NO lo frena): es un bug de sandbox, abrí el fix antes
   de marcar el test como esperado-falla.

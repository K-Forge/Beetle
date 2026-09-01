# Plan de finalización del MVP v0.1 de Doctor J/K

**Corte de auditoría:** 2026-08-31, zona `America/Bogota`
**Repositorio:** `K-Forge/Beetle`
**Fuente normativa:** proyecto, roadmap y tareas v4.0; issues #166–#222
**Rama de trabajo observada:** `AIprototipo` en `8592b99`
**Mejor rama recuperable:** `gate-d/modo-1` en `3638378`
**Restricción de esta entrega:** análisis y documento local; no se hizo commit,
push, PR, merge ni cambio remoto.

Este documento reemplaza como guía operativa el estado desactualizado de
`docs/plan-mvp.md` y `docs/progreso-mvp.md`. Esos dos archivos conservan valor
histórico, pero no deben usarse para afirmar qué está cerrado hoy.

---

## 1. Veredicto ejecutivo

El MVP **no está terminado ni operativo**. Hay una base considerable en ramas,
pero `main` y el VPS solo contienen el trigger original. La rama más avanzada
incluye módulos de Monitor, Detector, Recolector, Sanitizador, cliente LLM,
Informe e instalador, con 158 pruebas unitarias en verde; sin embargo, el punto
de entrada instalado todavía conecta cada snapshot a `log_snapshot`, no al
Detector ni al pipeline de Modo 1.

La distinción que debe conservar cualquier agente es esta:

| Nivel | Estado real |
|---|---|
| Código escrito | Fases 1–6 parcialmente implementadas en `gate-d/modo-1` |
| Código integrado | `main` solo tiene infraestructura y `trigger.sh` |
| Código desplegado | VPS en `main@6166bf9`; no existen unidades `doctorjk` instaladas |
| Criterios de issues | Solo #166–#172 aparecen cerrados; #173–#222 siguen abiertos |
| Modo 1 ejecutable | No: `main()` solo muestrea y registra |
| Modo 2 | No implementado |
| Modo 3 | No implementado; solo existen flags/configuración sin consumidor |
| Medición del producto | No existen las 42 corridas ni la matriz final |
| Distribución cerrada | No existe; además el repositorio remoto está público |

No se asigna un porcentaje único. Contar archivos o commits inflaría el avance:
un módulo aislado y probado no equivale a una capacidad instalada que satisface
su criterio de avance.

### 1.1 Bloqueadores P0

1. El repositorio remoto tiene `visibility=public`, en contradicción con la
   decisión cerrada de código privado/cerrado y con el criterio original de #166.
2. `gate-d/modo-1` no cablea el pipeline desde el ejecutable real.
3. La prueba de 24 horas de Gate B es inválida: sigue ejecutándose desde el
   2026-08-26 y sus 17.040 líneas solo dicen `muestra tomada`; no se instanció el
   Detector y no existe una sola transición registrada.
4. La recuperación de servicios no funciona con los contratos actuales:
   `normalize_snapshot()` emite solo servicios fallidos, mientras `Detector`
   interpreta una clave ausente como lectura no disponible y no como lectura
   sana. Un incidente de servicio quedaría activo indefinidamente.
5. `config.toml` no define servicios ni la asociación puerto↔servicio esperado;
   por tanto no hay forma completa de normalizar esos recursos.
6. `port_down` no representa el escenario `puerto_ocupado`: el parser actual
   descarta la identidad del proceso y considera sano el puerto si cualquier
   proceso escucha. La inconsistencia debe resolverse con un tipo interno nuevo,
   sin renombrar los contratos históricos.
7. El modelo de ejemplo de Gate D usa `gpt-oss-120b`; la documentación del propio
   proyecto fija el identificador `@cf/openai/gpt-oss-120b`.
8. Nunca se realizó una llamada real desde el pipeline a Cloudflare ni el cambio
   real al fallback configurado.
9. La instalación limpia, la reinstalación idempotente y el tiempo menor a 15
   minutos no fueron medidos.
10. No hay CI efectivo sobre el código de gates: el workflow existe en esas ramas,
   pero solo corre en PR o en pushes a `main`; no hay ningún PR abierto.
11. Las Fases 7–10 obligatorias siguen sin implementación ni evidencia.

---

## 2. Evidencia de la auditoría

### 2.1 Referencias remotas verificadas

La consulta se hizo por la API autenticada de GitHub porque `git fetch origin`
falló por falta de llave SSH aceptada en este entorno. Las referencias de GitHub
coinciden con las referencias `origin/*` locales:

| Rama | SHA | Relación con `main` | Decisión |
|---|---|---:|---|
| `main` | `6166bf9` | base | Rama protegida y desplegada; no contiene el MVP |
| `origin/dev` | `ed894dd` | +3, divergente | No fusionar completa; implementación temprana alternativa |
| `doctor/monitor.py` | `2c22aa2` | +1 | Ancestro de `origin/dev`; no fusionar |
| `AIprototipo` | `8592b99` | +6 | Ancestro de Gate C y Gate D; no fusionar por separado |
| `gate-c/sanitizador-uri` | `b513da3` | +7 | Ancestro directo de Gate D; no fusionar por separado |
| `gate-d/modo-1` | `3638378` | +16 | Única base razonable para recuperar el trabajo |

Historia relevante:

```text
main@6166bf9
├── origin/dev@ed894dd
│   └── monitor/trigger alternativos del PR #223, cerrado sin merge
└── AIprototipo@8592b99
    └── gate-c/sanitizador-uri@b513da3
        └── gate-d/modo-1@3638378
```

Consecuencias:

- Fusionar `AIprototipo`, luego Gate C y luego Gate D repetiría trabajo: Gate D
  ya contiene las otras dos ramas.
- Fusionar `origin/dev` encima de Gate D produciría conflictos en
  `monitor.py`, `trigger.sh` y `__init__.py`, y reintroduciría una arquitectura
  que Gate A ya reemplazó.
- La integración debe partir de `gate-d/modo-1`, revisar las ideas únicas de
  `origin/dev` y cerrar esa rama como supersedida; no hacer un merge ciego.
- No borrar ramas hasta que el código integrado esté en `main`, el PR esté
  auditado y exista una etiqueta de respaldo.

### 2.2 Pruebas locales reproducidas

Se extrajo cada rama en un directorio temporal y se ejecutó con CPython 3.11:

| Rama | Resultado pytest | Lectura correcta |
|---|---:|---|
| `AIprototipo` | 105 passed | Gates A–C antes del fix de URI |
| `gate-c/sanitizador-uri` | 111 passed | Gate C con credenciales de URI/Basic |
| `gate-d/modo-1` | 158 passed | Módulos aislados hasta instalador |

También pasaron `compileall` y `bash -n`. `shellcheck` no está instalado en la
máquina local, por lo que esa validación sigue pendiente. `git diff --check`
marca espacios finales deliberados usados como saltos de línea Markdown en
`docs/plan-mvp.md`; deben normalizarse antes de exigir el comando como gate.

La suite no incluye una prueba que arranque `main()` con configuración real y
demuestre el recorrido snapshot → señal → Detector → evidencia → sanitización →
sesión HTTP simulada → informe. Por eso 158 tests verdes no detectaron el hueco
principal.

### 2.3 Estado remoto de issues, PR y CI

- Único PR encontrado: #223, `dev → main`, cerrado sin merge.
- PR abiertos: cero.
- Issues cerrados: #166–#172.
- Issues abiertos: #173–#222, 50 en total.
- El ruleset `main protection` está activo sobre `main`.
- El último workflow de despliegue exitoso corresponde a `main@6166bf9`.
- El workflow `desplegar.yml` solo sincroniza el checkout de
  `/home/beetle/Beetle`; no actualiza `/opt/doctorjk` ni reinicia el producto.

### 2.4 Estado del VPS, comprobado por Tailscale

La inspección fue de solo lectura por Tailscale, no por el SSH público.

| Evidencia | Resultado |
|---|---|
| Repo | `/home/beetle/Beetle`, `main@6166bf9`, limpio |
| Unidades | `doctorjk.service` y `doctorjk-trigger.service`: no encontradas |
| Instalación | no existen `/opt/doctorjk`, `/etc/doctorjk` ni `/var/lib/doctorjk` |
| Gate B | dos procesos sueltos desde 2026-08-26 |
| Log Gate B | 17.040 muestras, 2,2 MB, 0 incidentes/transiciones/candidatos |
| Cableado de Gate B | `on_snapshot=log_snapshot` |
| Trigger de Gate B | proceso activo; archivo de log vacío |

La prueba Gate B no puede declararse exitosa ni fallida respecto a falsos
positivos: nunca evaluó el Detector. Debe detenerse de forma controlada,
archivarse como corrida inválida y repetirse después de corregir el ejecutable.

---

## 3. Estado por fase e issue

| Fase | Issues | Código disponible | Criterio realmente satisfecho | Estado |
|---|---|---|---|---|
| 0 | #166–#170 | Infraestructura, restore, carga y Cloudflare documentados | VPS y workflows existen | Reabrir control de #166 por visibilidad pública |
| 1 | #171–#173, #222 | Monitor, trigger, modelos, CLI/FIFO | Unit tests; monitor aislado | Parcial: el proceso no normaliza ni detecta |
| 2 | #174–#178 | `detector.py`, config y tests | Lógica aislada | Parcial: sin ejecución real; Gate B inválido |
| 3 | #179–#185 | Recolector, evidencia cruda, sanitizador y tests | Gate C reporta 0 fugas en corpus sembrado | Casi lista, pero falta ventana +1 min real y reintegración |
| 4 | #186–#190 | Cliente HTTP, caché, backoff y fallback | Mocks | Parcial: sin sesión real, proveedor real ni contrato final |
| 5 | #191–#194 | Prompt v1 | Solo estructura estática | Falta iterar contra escenarios y medir alucinación/lenguaje |
| 6 | #195–#198 | Informe, rotación, units e instalador | `systemd-analyze verify` reportado | Parcial: no instalado, no idempotencia ni tiempo medido |
| 7 | #199–#202 | Solo README de carpeta | Ninguno | Sin empezar |
| 8 | #203–#206 | Solo README/protocolo | Ninguno | Sin empezar |
| 9 | #207–#215 | Flags/config anticipados | Ninguna salvaguarda funcional | Sin empezar |
| 10 | #216–#221 | Documentación de proyecto y restore | Contexto parcial | Falta arquitectura, README cliente, paquete, demo y presentación |

### 3.1 Defectos concretos que deben corregirse antes del primer merge

1. `doctorjk/main.py` importa Detector y pipeline, pero `build_app()` conserva
   `on_snapshot=log_snapshot`; los imports y helpers son código muerto en runtime.
2. `main.py` no llama `load_config()`, no lee `diagnosticador.md`, no crea
   `requests.Session` y no usa los umbrales del cliente.
3. `servicio_ciclos`, `puerto_timeout_s`, `modo_remediacion`, `auto_fix`,
   `dry_run` y `timeout_comando_s` se cargan pero no afectan el comportamiento.
4. No existen claves para la lista de servicios ni para asociar un puerto con el
   servicio que debería poseerlo.
5. El Detector usa un único número de ciclos; no consume los ciclos específicos
   de servicio ni convierte el timeout del puerto a persistencia.
6. `systemctl --failed` no distingue un servicio configurado sano de uno detenido
   limpiamente. Además, la desaparición de un servicio de esa lista no produce
   señal sana; contradice el contrato del Detector.
7. El monitor solo conserva dirección/puerto de `ss`; no puede distinguir
   `port_down` de `port_occupied` ni comprobar quién debería escuchar.
8. `collect_evidence()` consulta `--until confirmed_at+1m` inmediatamente.
   `journalctl` no espera a que transcurra ese minuto: la ventana posterior no se
   obtiene realmente.
9. El cliente implementa un intento inicial más tres reintentos. La tarea #188
   dice “máximo 3 intentos” pero también exige esperas 1/2/4; la especificación es
   internamente contradictoria y debe corregirse antes de cerrar el issue.
10. `llm.py` y `main.py` capturan `Exception`, prohibido por las convenciones.
11. Un 401/403 lanza `LLMConfigError` y el pipeline actual puede terminar sin
    informe; el criterio de fallback exige no guardar silencio.
12. Gran parte de los identificadores Python y Bash está en español. Los nombres
    de archivo deben seguir en español, pero funciones, variables, parámetros y
    constantes deben migrar a inglés antes de declarar el código entregable.
13. `doctorjk.service` no recibe la ruta de `config.toml`; su `Documentation=`
    apunta a un README que el instalador no copia.
14. El ejemplo de modelo de Cloudflare no coincide con el identificador fijado en
    tareas/proyecto.
15. La CI no tiene prueba integral del ejecutable, test de instalación ni análisis
    de secretos.
16. `docs/progreso-mvp.md` afirma Gate D cerrado y Gate B en curso hasta una fecha
    ya vencida; debe corregirse, no conservarse como estado vigente.

---

## 4. Decisiones que deben quedar explícitas antes de programar

### D1 — Privacidad del repositorio

**Decisión por defecto:** devolver el repositorio a privado antes de subir más
código. Es la única opción compatible con las decisiones cerradas.

**Trade-off:** cambiar visibilidad puede afectar enlaces, Actions o forks ya
creados; no recupera el código que ya fue público. Por eso se debe acompañar de
auditoría de secretos e historial. Esta acción es remota y requiere autorización
humana explícita; un agente no la ejecuta por inferencia.

### D2 — Reintentos del LLM

La tarea debe escoger una semántica verificable:

- recomendada: 1 intento inicial + 3 reintentos, con esperas 1/2/4;
- alternativa: 3 intentos totales, con esperas 1/2.

La implementación existente sigue la primera. Actualizar #188 y los documentos
si se conserva; no cerrar el issue mientras la redacción siga contradiciéndose.

### D3 — Carga alta

Mantener `high_load` como dato informativo, no como incidente, hasta que producto
apruebe umbral y persistencia. Ninguno de los nueve escenarios positivos tiene
carga alta como causa raíz y crear un umbral ahora elevaría falsos positivos.
Actualizar #173 para que no exija un mapeo operativo sin criterio aprobado.

### D4 — Formato de distribución

Para este agente local, `.deb` es preferible a Docker: necesita journal, systemd,
sistema de archivos y privilegios controlados del host. Si se exige ocultar el
fuente Python, aprobar una herramienta de compilación como dependencia **de
build**, no de runtime, y documentar que ningún empaquetado Python impide por
completo la ingeniería inversa.

Si el cronograma obliga a recortar #218, el MVP académico se entrega mediante el
instalador y la deuda se declara. No se puede afirmar que la distribución cerrada
está resuelta en ese caso.

### D5 — Modelos del Modo 3

Construir primero el contrato planificador/ejecutor independiente del proveedor.
Usar gpt-oss-120b durante desarrollo. La dupla Kimi K2.6/Qwen3-30B-A3B solo se
activa al cierre si disponibilidad, formato y costo se verifican; esos datos no
se deben inferir de la documentación histórica.

---

## 5. Protocolo obligatorio para el agente que ejecute este plan

1. Leer `CONTEXTO-IA.md` y el README de cada carpeta tocada.
2. Trabajar desde el último `main` remoto verificado; si no se puede actualizar,
   detener la integración y registrar el SHA disponible.
3. No mezclar cambios funcionales, refactors de nombres y documentación en un
   mismo commit.
4. Escribir el test que expone el defecto antes del fix.
5. Mantener nombres de módulos/archivos en español e identificadores internos en
   inglés. Comentarios, docstrings, logs y documentación van en español.
6. No agregar dependencias de runtime distintas de `requests`.
7. No usar `shell=True`, `except Exception`, `print` en Python ni estado global.
8. Ningún payload sale sin `SanitizedEvidence`.
9. No ejecutar escenarios destructivos fuera del VPS compartido y de una ventana
   coordinada. El tráfico siempre usa `hey -z 2m` como máximo.
10. No crear una segunda VM ni un segundo boot volume de 150 GB.
11. No crear un sexto snapshot.
12. No cerrar issues por existencia de código: exigir su criterio de avance.
13. No hacer push, crear PR, mergear, cambiar visibilidad ni cerrar issues sin la
    autorización remota vigente del usuario.
14. Antes de cada commit ejecutar, según los archivos existentes:

```bash
python3 -m compileall doctorjk pruebas/unitarias
python3 -m pytest pruebas/unitarias -q
bash -n doctorjk/trigger.sh instalador/*.sh scripts-fix/*.sh demo/*.sh
shellcheck doctorjk/trigger.sh instalador/*.sh scripts-fix/*.sh demo/*.sh
git diff --check
git status --short
```

15. Antes de cada merge confirmar que no hay `.env`, tokens, IPs reales, rutas de
    usuario, informes reales ni evidencia cruda en el diff.

---

## 6. Estrategia de ramas, commits y merges

### 6.1 Preparación local

No trabajar directamente sobre `main`, `dev` ni las ramas de gate existentes.

```bash
git fetch origin
git switch --create mvp/integracion-modo-1 gate-d/modo-1
git merge-base --is-ancestor AIprototipo HEAD
git merge-base --is-ancestor gate-c/sanitizador-uri HEAD
```

Si `git fetch` sigue fallando por SSH, corregir la autenticación o usar un remoto
HTTPS autenticado aprobado; no continuar basándose en referencias antiguas.

No ejecutar:

```bash
git merge origin/dev
git merge AIprototipo
git merge gate-c/sanitizador-uri
```

Las dos últimas ya son ancestros. `origin/dev` queda supersedida salvo que una
revisión por commit identifique una corrección ausente; en ese caso se reaplica
manualmente como commit nuevo y probado, no por merge.

### 6.2 PR previstos

| Orden | Rama | Base | Alcance | Merge permitido cuando |
|---:|---|---|---|---|
| 1 | `mvp/integracion-modo-1` | `gate-d/modo-1` → `main` | Recuperación, wiring real, Gates A–E | Modo 1 instalado y medido |
| 2 | `mvp/modo-2` | `main` | #199–#202 | 4 scripts probados e idempotentes |
| 3 | `mvp/escenarios-medicion` | `main` | #203–#206 | Oráculos previos + 42 corridas base |
| 4 | `mvp/modo-3-plan-seguro` | `main` | #207–#210 | plan, allowlist, dry-run y opt-in |
| 5 | `mvp/modo-3-ejecucion` | `main` | #211–#214 | aborto, auditoría y >85% |
| 6 | `mvp/cierre-v0.1` | `main` | #215–#220 | comprensión, docs, paquete/demo |

Usar PR con merge commit para conservar la procedencia de los gates. No hacer
push directo a `main`, aunque una cuenta administradora pueda saltar el ruleset.
No borrar ramas al hacer merge; etiquetar primero el hito correspondiente.

### 6.3 Comandos remotos futuros

Estos comandos **no están autorizados por esta entrega**. Solo sirven como
secuencia cuando el usuario levante expresamente la restricción de no subir nada:

```bash
git push --set-upstream origin mvp/integracion-modo-1
gh pr create --base main --head mvp/integracion-modo-1
gh pr checks --watch <NUMERO_PR>
gh pr merge <NUMERO_PR> --merge
```

Después de cada merge:

1. verificar el SHA de `origin/main`;
2. verificar el workflow de CI;
3. verificar el workflow de sincronización del repo del VPS;
4. recordar que sincronizar `/home/beetle/Beetle` **no actualiza** la instalación
   de `/opt/doctorjk`;
5. desplegar el paquete/instalador mediante el procedimiento controlado del gate.

---

## 7. Ejecución detallada

## Gate 0 — Contención, verdad documental y base integrable

### 0.1 Proteger el activo de código cerrado

**Responsable:** persona administradora del repositorio.
**Acción remota:** requiere aprobación explícita.

1. Confirmar que hacer privado el repositorio no rompe la entrega universitaria.
2. Cambiar visibilidad a privada.
3. Revisar colaboradores, deploy keys, Actions, forks y artefactos.
4. Auditar todo el historial por secretos; rotar cualquier credencial encontrada.
5. Verificar nuevamente `visibility=private` por API.
6. Reabrir #166 o crear un incidente de regresión hasta completar los pasos.

**Salida:** evidencia de visibilidad privada y auditoría, sin publicar secretos en
el issue.

### 0.2 Detener y archivar la Gate B inválida

No matar procesos por patrón amplio. Resolver primero los PIDs exactos de:

```text
python3 -m doctorjk.main --interval 30 --log-level INFO
bash /opt/gate-b/doctorjk/trigger.sh
```

1. Guardar inicio, fin, número de muestras, tamaño y SHA del código usado.
2. Marcar la corrida como `INVALIDA_SIN_DETECTOR`; no calcular falsos positivos.
3. Detener primero el trigger y luego el monitor con SIGTERM.
4. Confirmar que ambos terminaron.
5. Conservar los logs hasta que el resumen sanitizado quede versionado.
6. Limpiar `/opt/gate-b` solo después de aprobación y respaldo.

**No cuenta como:** validación de #174–#178.

### 0.3 Corregir la fuente de verdad

Actualizar `docs/progreso-mvp.md` con la auditoría actual y marcar
`docs/plan-mvp.md` como plan histórico supersedido por este archivo. Corregir el
README raíz, que describe Detector/Recolector/LLM como no implementados aunque sí
existen en ramas.

**Commits:**

```text
docs(mvp): record the verified branch and VPS state
docs(readme): align the project status with the integration branch
```

**Gate:** ningún documento afirma Gate B/D/E cerrado sin evidencia válida.

---

## Gate 1 — Recuperar y sanear Gates A–C

### 1.1 Congelar comportamiento con tests de regresión

Agregar tests que fallen con el código actual:

- `main()` carga configuración y prompt;
- un snapshot sano de servicio produce una señal `crossed=False`;
- un servicio falla N ciclos, confirma una vez, se recupera N ciclos y resuelve;
- un puerto configurado se normaliza sano/caído;
- una categoría no disponible no se interpreta como sana;
- dos recursos mantienen estado independiente;
- una señal repetida no genera segundo informe.

**Commit:**

```text
test(main): expose missing runtime pipeline wiring
```

### 1.2 Completar configuración de recursos

Agregar al TOML de cliente, con validación fail-fast. Cada puerto debe indicar
qué servicio se espera que lo posea para diferenciar ausencia de ocupación:

```toml
servicios_vigilados = ["nginx.service", "postgresql.service"]
puertos_vigilados = [
  { puerto = 80, servicio = "nginx.service" },
  { puerto = 5432, servicio = "postgresql.service" },
  { puerto = 8000, servicio = "beetle-app.service" },
]
```

Reglas:

- listas no vacías, sin duplicados;
- puertos entre 1 y 65535, sin duplicados y con servicio configurado;
- unidades sin espacios, `/`, `..` ni metacaracteres;
- mantener `service_cycles` y convertir `port_timeout_s` a ciclos con
  `ceil(timeout/interval)`;
- disco y memoria usan `persistence_cycles`;
- carga queda informativa por D3.

**Commit:**

```text
feat(config): add validated monitored resources
```

### 1.3 Corregir normalización y Detector

1. Muestrear el estado de cada servicio configurado; no inferir “sano” solo
   porque no aparece en `systemctl --failed`.
2. Emitir una señal por cada servicio configurado, tanto activo como inactivo.
3. Emitir `port_down` cuando nadie escucha y un nuevo tipo interno
   `port_occupied` cuando el servicio esperado no está activo pero el puerto sí
   está ocupado. El nombre nuevo va en inglés y la inconsistencia con
   `puerto_ocupado` se documenta en el clasificador.
4. Conservar `port_down` porque ya está fijado por #173; no reutilizarlo con una
   semántica falsa.
5. Inyectar persistencia por tipo de señal en el Detector.
6. Registrar en INFO transiciones y supresiones exigidas por #178; usar DEBUG
   para muestras completas y evitar datos sensibles.
7. Probar recuperación, cooldown y reprocesamiento después de resolver.

**Commits:**

```text
fix(monitor): emit complete health signals for configured resources
feat(detector): apply persistence by signal type
test(detector): cover service recovery and per-type persistence
```

### 1.4 Alinear identificadores y manejo de errores

Hacer refactor mecánico por módulo, sin cambiar comportamiento:

- variables, funciones, parámetros, clases privadas y constantes en inglés;
- comentarios/docstrings/logs permanecen en español;
- reemplazar `except Exception` por excepciones concretas;
- justificar cada `except OSError` y no silenciar con `pass` sin comentario;
- nombres de archivo, claves TOML y claves históricas permanecen como están.

**Commits separados:**

```text
refactor(config): align internal identifiers with project conventions
refactor(detector): align internal identifiers with project conventions
refactor(recolector): align internal identifiers with project conventions
refactor(sanitizador): align internal identifiers with project conventions
refactor(llm): align internal identifiers with project conventions
refactor(informe): align internal identifiers with project conventions
refactor(main): align orchestration identifiers with project conventions
refactor(instalador): align shell identifiers with project conventions
```

**Gate:** suite verde después de cada commit; `git diff` del refactor no contiene
cambios funcionales deliberados.

---

## Gate 2 — Hacer real el Modo 1

### 2.1 Construir el runtime desde configuración

`main.py` debe ser composition root, no lógica de los módulos:

1. Aceptar `--config` y `--prompt` con defaults instalados.
2. Cargar `AppConfig` una vez al arranque.
3. Leer el prompt una vez y fallar con mensaje accionable si no existe.
4. Crear una `requests.Session` real e inyectarla al cliente LLM.
5. Instanciar un único Detector de larga vida.
6. Crear un callback de snapshot que:
   - normaliza con config;
   - evalúa el Detector;
   - procesa solo transiciones nuevas a `INCIDENT`;
   - no vuelve a procesar incidentes activos;
   - registra resolución sin invocar LLM.
7. Usar el intervalo del TOML salvo override CLI explícito.
8. Aplicar `command_timeout_s` a Monitor y Recolector.
9. Mantener el FIFO como fuente de despertar, no como portador de log crudo.
10. Cerrar limpiamente sesión, descriptor FIFO y señal SIGTERM.

**Commit:**

```text
feat(main): wire the diagnostic runtime from configuration
```

### 2.2 Obtener realmente la ventana +1 minuto

No bloquear el polling 60 segundos ni consultar el futuro como si ya existiera.

Implementar una cola acotada de incidentes pendientes:

1. al confirmar, conservar el incidente con `collect_after=confirmed_at+1m`;
2. el loop espera el menor tiempo entre próximo polling, FIFO e incidente debido;
3. al vencer, recolecta la ventana completa −5/+1;
4. procesa incidentes en orden y limita la cola para no agotar memoria;
5. si el reloj salta o el servicio reinicia, registrar el incidente pendiente y
   degradar a la evidencia disponible; no inventar el minuto faltante.

El informe debe seguir apareciendo antes de 120 segundos.

**Commit:**

```text
fix(recolector): capture the complete post-incident window
```

### 2.3 Cerrar el contrato LLM

1. Corregir el modelo Cloudflare a `@cf/openai/gpt-oss-120b`.
2. Resolver D2 y actualizar tests/documentos.
3. Capturar excepciones concretas de `requests`.
4. Respetar `Retry-After` para 429 si es válido; usar backoff si no existe.
5. Ante token ausente, 401/403, timeout agotado o respuesta rota, producir
   fallback sanitizado y siempre intentar escribir informe.
6. No registrar headers, token ni payload completo.
7. Mantener la caché solo con opt-in; modo 700 para directorio y 600 para archivos.
8. Probar Cloudflare real con evidencia sintética sanitizada.
9. Probar el segundo backend solo tras verificar endpoint/modelo actual.

**Commits:**

```text
fix(llm): align provider identifiers and retry semantics
fix(llm): produce a fallback for permanent provider failures
test(llm): verify the real provider contract with sanitized input
```

El tercer commit solo se crea si contiene un test de integración opt-in sin
credenciales ni respuesta real versionadas.

### 2.4 Prueba vertical desde el ejecutable

Agregar una prueba de integración local que invoque el mismo builder de
producción con fronteras simuladas y demuestre:

```text
config -> snapshot -> señales -> candidato -> incidente
       -> evidencia cruda 600 -> SanitizedEvidence -> HTTP simulado
       -> informe Markdown -> rotación por pares
```

Casos obligatorios:

- éxito del modelo;
- modelo caído y fallback;
- token ausente;
- fallo parcial de una herramienta del sistema;
- fallo al escribir evidencia;
- fallo al escribir informe sin tumbar el loop;
- ningún dato sensible llega a la sesión simulada;
- dos incidentes en el mismo segundo no pisan archivos.

**Commit:**

```text
test(pipeline): cover the executable Mode 1 flow end to end
```

**Gate:** un `doctorjk --once` de diagnóstico controlado y una corrida residente
producen comportamiento documentado; ya no existe `on_snapshot=log_snapshot` en
producción.

---

## Gate 3 — Instalación, systemd y validación real de Gates A–E

### 3.1 Corregir unidades e instalador

1. Pasar rutas de config/prompt explícitamente en `ExecStart`.
2. Corregir o instalar la ruta usada por `Documentation=`.
3. Verificar lectura de journal como `doctorjk`.
4. Verificar escritura exclusiva bajo `/var/lib/doctorjk` y FIFO bajo `/run`.
5. Mantener config y `.env` en reinstalación.
6. No imprimir el secreto ni aceptar token como argumento visible en `ps`.
7. Eliminar el `pip --upgrade` innecesario si no aporta al contrato; fijar y
   verificar dependencias de build para reproducibilidad.
8. Probar desinstalación conservando datos y borrado solo con opt-in explícito.
9. Añadir tests de instalador en entorno aislado donde sea posible y conservar la
   prueba real para el VPS.

**Commits:**

```text
fix(instalador): start the configured diagnostic runtime
test(instalador): cover idempotent install and data-preserving removal
```

### 3.2 Validar en el único VPS

Ventana coordinada y snapshot confirmado antes de modificar:

1. finalizar/archivar Gate B inválida;
2. restaurar mediante el workflow documentado si hace falta un estado limpio;
3. entrar por Tailscale primero;
4. instalar desde el candidato de integración;
5. cronometrar desde comando inicial hasta ambas unidades activas;
6. confirmar tiempo <15 minutos;
7. ejecutar el instalador una segunda vez y comparar config, secreto e informes;
8. verificar `systemd-analyze verify`, hardening, reinicio y SIGTERM;
9. comprobar consumo CPU <1% en estado sano;
10. hacer llamada real a Cloudflare con evidencia sintética sanitizada;
11. provocar los cuatro incidentes básicos de Detector de forma controlada;
12. ejecutar 24 horas sanas con Detector realmente cableado;
13. calcular falsos positivos desde transiciones, no desde líneas de muestreo;
14. guardar solo resultados sanitizados en Git.

**Importante:** `systemctl stop postgresql` es una parada limpia y no garantiza un
evento de error. Para el escenario de caída usar un mecanismo que simule fallo
real y tenga restauración documentada.

**Commits de evidencia:**

```text
test(detector): record the valid 24-hour VPS run
test(instalador): record the clean timed installation
docs(mvp): close the Mode 1 acceptance gate
```

### 3.3 Primer merge

Abrir PR `mvp/integracion-modo-1 → main`. Vincular #173–#198 y #222, pero cerrar
solo los issues cuyo criterio esté demostrado. Exigir:

- 100% tests de sanitizador;
- suite completa verde;
- CI verde en PR;
- revisión de privacidad;
- evidencia de VPS;
- documentación corregida;
- ninguna credencial ni evidencia real en diff.

Después del merge, etiquetar `v0.1.0-alpha1`. No llamar a esto MVP final: solo es
el hito alfa de Modo 1.

---

## Gate 4 — Modo 2 determinista (#199–#202)

### 4.1 Contratos y privilegios

Crear `clasificador.py` y `remediador.py` con contratos explícitos. Resolver la
mezcla histórica de nombres mediante un mapeo documentado, no renombrando claves
existentes por cuenta propia:

```text
SignalType.DISK_FULL      -> disco_lleno       -> fix_disco.sh
SignalType.SERVICE_FAILED -> servicio_caido    -> fix_servicio.sh
SignalType.MEMORY_LOW     -> memoria_agotada   -> fix_memoria.sh
SignalType.PORT_OCCUPIED  -> puerto_ocupado    -> fix_puerto.sh
```

`SignalType.PORT_DOWN` permanece como señal diagnóstica sin script hasta que
producto defina una corrección determinista distinta. No mapearlo a
`puerto_ocupado`: son condiciones diferentes.

El instalador genera sudoers con comandos exactos. Nunca concede shell ni sudo
genérico al usuario `doctorjk`.

### 4.2 Scripts

Crear `comun.sh` y cuatro scripts. Cada uno debe:

- validar precondición;
- aceptar solo servicio/ruta/puerto preconfigurado;
- respetar `DOCTORJK_DRY_RUN=1`;
- ser idempotente;
- ejecutar acciones acotadas;
- verificar postcondición;
- devolver 0 solo si quedó resuelto;
- escribir mensajes en español a stdout/stderr;
- no usar `rm -rf` ni variables sin comillas.

Decisiones por script:

- disco: listar candidatos y aplicar política de retención bajo raíces exactas;
  no borrar “el archivo más grande” sin política;
- servicio: iniciar/reiniciar solo unidades configuradas;
- memoria: actuar solo sobre una unidad previamente aprobada cuyo cgroup sea el
  consumidor anómalo. Si no hay una unidad aprobada identificable, escalar; no
  matar procesos arbitrarios ni escribir a `drop_caches`. El escenario de demo
  debe ejecutar el consumidor como una unidad de prueba explícitamente permitida;
- puerto: detener solo una unidad conflictiva previamente aprobada y reiniciar el
  servicio esperado. El listener de demo debe ser una unidad identificable de
  prueba; ante un PID arbitrario o identidad incierta, escalar sin ejecutar.

### 4.3 Orquestación y auditoría

El Modo 2 se ejecuta solo con `modo_remediacion="scripts"` y opt-in efectivo.
Registrar inicio/fin, argv, código, stdout, stderr y verificación, sanitizando
salidas antes de journald/informe. Si falla, no reintentar automáticamente y
marcar “corrección fallida — escalar”.

**Commits:**

```text
feat(scripts-fix): add idempotent deterministic corrections
feat(clasificador): map incident types to approved scripts
feat(remediador): execute and audit deterministic corrections
test(remediador): verify post-correction outcomes and escalation
fix(instalador): install least-privilege remediation policy
```

**Gate VPS:** 4/4 básicos resueltos en menos de 2 minutos, ejecución duplicada no
empeora el servidor y un tipo desconocido no ejecuta nada.

Mergear `mvp/modo-2 → main` y etiquetar `v0.1.0-alpha2`.

---

## Gate 5 — Escenarios y línea base de medición (#203–#206)

### 5.1 Provocadores reproducibles

Crear 9 positivos y 5 negativos. Cada script incluye propósito, precondición,
causa esperada, duración, limpieza y criterio de restauración.

Controles específicos:

- disco: calcular espacio requerido desde `df`; el VPS tiene ~140 GB libres, no
  usar el valor obsoleto de 18 GB; `fallocate` debe apuntar a un archivo exacto;
- memoria: imponer límite temporal y reserva máxima para no perder acceso;
- servicio/puerto: guardar estado previo y restaurarlo;
- config rota: respaldar archivo antes y restaurar permisos/contenido;
- cascada: documentar una sola causa raíz y síntomas derivados;
- negativos: no cruzar umbrales sostenidos;
- tráfico: `hey -z 2m`, nunca permanente.

### 5.2 Oráculos antes de ejecutar

Crear un Markdown por escenario en `pruebas/esperados/` con:

- síntoma esperado;
- causa raíz;
- causas descartadas;
- guía correcta;
- señales esperadas/no esperadas;
- resultado Modo 2;
- resultado Modo 3 cuando exista;
- criterio de limpieza.

El commit de oráculos debe preceder al commit de resultados.

### 5.3 Corridas y matriz

Ejecutar 9×3 positivos + 5×3 negativos. Registrar:

- hora de provocación, detección, confirmación e informe;
- versión de código, prompt, modelo y config;
- detección sí/no;
- causa correcta sí/no;
- guía útil sí/no;
- falso positivo sí/no;
- latencia;
- resultado Modo 2;
- errores parciales.

No versionar evidencia cruda. Sanitizar informes usados como muestra.

**Commits:**

```text
feat(demo): add reproducible positive and negative scenarios
test(esperados): define scenario oracles before execution
test(resultados): record the three-run baseline matrix
```

**Gate:** detección >90%, causa raíz >80%, falsos positivos <10%, informe <120 s
y guía útil >70%. Si falla una métrica, corregir el componente causal y repetir
la tanda afectada; no editar el oráculo después de ver el resultado.

Mergear `mvp/escenarios-medicion → main`.

---

## Gate 6 — Modo 3 con las cinco salvaguardas (#207–#214)

### 6.1 Plan estructurado

Agregar a `modelos.py` dataclasses inmutables para `CorrectionStep`,
`CorrectionPlan`, `ExecutionResult` y estado de escalamiento.

Preferir `argv: tuple[str, ...]` a una cadena de shell. Cada paso incluye:

- argv de acción;
- argv/verificación esperada;
- resultado esperado estructurado;
- condición de continuar;
- condición de abortar;
- justificación;
- timeout.

`planificador.py` valida JSON estricto, tipos, límite de pasos y tamaño. Un campo
desconocido, faltante o inválido invalida todo el plan y no ejecuta nada.

**Commit:**

```text
feat(planificador): parse strict structured correction plans
```

### 6.2 Salvaguarda 1 — Lista blanca

`lista_blanca.py` valida argv y recursos exactos:

- `systemctl start|restart <unidad-configurada>`;
- `truncate -s 0 <archivo-bajo-raíz-aprobada>`;
- eliminación no recursiva de archivo regular bajo rutas aprobadas;
- verificaciones de solo lectura explícitas.

Rechazar metacaracteres, pipes, redirecciones, `rm -rf`, `dd`, `mkfs`,
`chmod 777`, rutas relativas, symlinks que escapen, servicios no configurados y
argumentos extra. No implementar la excepción insegura de `sync; echo ...` de
#208. No incluir instalación arbitraria de paquetes en el MVP.

**Commit:**

```text
feat(lista_blanca): validate structured commands and resources
```

### 6.3 Salvaguardas 2 y 3 — dry-run y opt-in

- instalación nueva: Modo 1, `auto_fix=false`, `dry_run=true`;
- modo automático sin opt-in: solo diagnóstico;
- modo automático con dry-run: genera/valida/audita, no ejecuta;
- ejecución real: `modo_remediacion="automatico"`, opt-in explícito y
  `dry_run=false`;
- resolver precedencia CLI/TOML y registrarla sin ambigüedad;
- marcar informe `[DRY-RUN] Ningún comando fue ejecutado`.

**Commit:**

```text
feat(remediador): enforce dry-run and explicit automatic-fix opt-in
```

### 6.4 Salvaguarda 4 — Ejecución y aborto

`ejecutor.py` usa `subprocess.run` con lista, `check=False`, timeout y sin shell.
Por cada paso:

1. validar allowlist otra vez;
2. ejecutar acción;
3. capturar resultado;
4. ejecutar verificación aprobada;
5. continuar solo si coincide;
6. abortar al primer resultado inesperado;
7. no reintentar después del aborto;
8. dejar estado y pasos pendientes para escalamiento.

**Commits:**

```text
feat(ejecutor): execute validated correction plans step by step
feat(ejecutor): abort and escalate on the first unexpected result
```

### 6.5 Salvaguarda 5 — Auditoría completa

Registrar timestamp, argv, código, stdout, stderr, verificación, decisión y
justificación en journald e informe. Sanitizar stdout/stderr antes de ambos
destinos; nunca registrar token, headers ni evidencia cruda.

**Commit:**

```text
feat(remediador): persist complete sanitized Mode 3 audit trails
```

### 6.6 Pruebas y medición

Pruebas negativas mínimas:

- `rm -rf /`;
- pipe y redirección;
- traversal y symlink fuera de raíz;
- servicio no permitido;
- timeout;
- paso 2 falla y pasos 3–4 no corren;
- respuesta JSON malformada;
- stdout con secreto;
- dry-run no cambia estado;
- ausencia de auto-fix no cambia estado.

Ejecutar primero todos los escenarios en dry-run y después, con snapshot y
ventana coordinada, la medición real. Agregar columna de corrección automática a
la matriz. Meta >85%.

**Commits:**

```text
test(lista_blanca): reject destructive and escaping commands
test(ejecutor): verify dry-run abort and audit safeguards
test(resultados): record automatic remediation success metrics
```

Mergear PR 4 y PR 5 solo si las cinco salvaguardas están completas. No dividir
una salvaguarda entre “ahora” y “después”. Etiquetar `v0.1.0-beta1`.

---

## Gate 7 — Comprensibilidad, documentación, distribución y demo (#215–#220)

### 7.1 Comprensibilidad

Entregar cinco informes sanitizados a 3–5 personas no técnicas. Usar formulario
con preguntas objetivas: qué pasó, causa, primer paso, riesgo y si podrían seguir
la guía. Meta >80%. Registrar método y resultados agregados, no datos personales.

**Commit:**

```text
test(comprensibilidad): record external report comprehension results
```

### 7.2 Documentación de producto

Crear `docs/arquitectura.md` con contratos, flujo, seguridad, estados, archivos y
trade-offs. Reescribir README para una persona sin acceso al fuente:

- qué es y qué no es;
- prerrequisitos;
- instalación <15 min;
- configuración completa;
- consulta de informes/journald;
- activación de Modos 2 y 3;
- lista blanca pública;
- dry-run, aborto y auditoría;
- actualización/desinstalación;
- troubleshooting;
- privacidad y limitaciones del sanitizador.

**Commits:**

```text
docs(arquitectura): document component contracts and safety boundaries
docs(readme): add complete installation usage and troubleshooting guide
```

### 7.3 Distribución

Si #218 no se recorta:

1. aprobar herramienta de build;
2. producir `.deb` ARM64 reproducible;
3. incluir binario/paquete, prompts, scripts, units, config, licencia y checksum;
4. instalar sin clonar Git;
5. actualizar sin perder config/datos;
6. desinstalar conservando informes por defecto;
7. medir otra vez <15 min;
8. documentar limitaciones de protección del código.

**Commits:**

```text
chore(instalador): package the ARM64 proprietary distribution
docs(instalador): document package verification and lifecycle
```

Si se recorta, registrar decisión explícita y entregar con `install.sh`; no crear
los commits anteriores ni marcar #218 cerrado.

### 7.4 Demo y presentación

- demo de 2–3 escenarios en menos de 10 minutos;
- tráfico de fondo máximo 2 minutos;
- Modo 3 en dry-run para la presentación salvo ventana aprobada;
- 3–5 informes reales sanitizados de respaldo;
- guion con tiempos y restauración;
- dos ensayos completos;
- presentación de máximo 20 slides con problema, cliente, solución, seguridad,
  métricas, producto y roadmap.

**Commits:**

```text
feat(demo): add the rehearsed end-to-end demonstration flow
docs(presentacion): add the final evidence-based project deck
```

#221 queda fuera del MVP. No crear backend ni panel.

Mergear `mvp/cierre-v0.1 → main` y crear la release `v0.1.0` solo después del
checklist final.

---

## 8. Checklist de release v0.1.0

### Git y trazabilidad

- [ ] Repositorio privado o excepción de producto documentada.
- [ ] `main` contiene todos los PR aprobados y CI verde.
- [ ] No quedan commits útiles solo en ramas sin integrar.
- [ ] `origin/dev` y gates están marcadas supersedidas, no borradas antes del tag.
- [ ] Issues cerrados únicamente con evidencia de su criterio.
- [ ] Tag `v0.1.0` apunta al commit probado.

### Funcionalidad

- [ ] Monitor y trigger alimentan al mismo Detector residente.
- [ ] Persistencia, resolución, cooldown y deduplicación funcionan.
- [ ] Ventana de evidencia −5/+1 minuto es real.
- [ ] Evidencia cruda 600 queda local.
- [ ] Solo `SanitizedEvidence` llega al cliente HTTP.
- [ ] Cloudflare real y backend alternativo cambian por configuración.
- [ ] Fallback siempre deja informe.
- [ ] Rotación conserva 30 pares informe/evidencia.
- [ ] Modo 2 resuelve 4 básicos y verifica resultado.
- [ ] Modo 3 conserva las cinco salvaguardas.

### Operación y seguridad

- [ ] Usuario `doctorjk` sin login y privilegios mínimos.
- [ ] Sudoers exacto, sin shell genérico.
- [ ] Sin `shell=True`, `except Exception`, `print` ni secretos en logs.
- [ ] Identificadores internos en inglés; comentarios/logs en español.
- [ ] systemd reinicia y termina limpiamente.
- [ ] Instalación y reinstalación <15 min, sin pisar config.
- [ ] Desinstalación conserva datos salvo opt-in.
- [ ] No hay credenciales, IPs reales, rutas de usuario o evidencia cruda en Git.

### Métricas

- [ ] 42 corridas con oráculos escritos antes.
- [ ] Detección >90%.
- [ ] Causa raíz >80%.
- [ ] Falsos positivos <10%.
- [ ] Tiempo a informe <120 s.
- [ ] Guía útil >70%.
- [ ] Corrección automática >85%.
- [ ] Comprensibilidad >80%.

### Entrega

- [ ] README permite instalar y operar sin ver el código.
- [ ] `docs/arquitectura.md` explica todos los contratos.
- [ ] Lista blanca documentada públicamente.
- [ ] Demo <10 min ensayada dos veces.
- [ ] Informes sanitizados de respaldo disponibles.
- [ ] Distribución cerrada completada o recorte de #218 declarado.
- [ ] #221 no entró al alcance.

---

## 9. Orden inmediato de trabajo

La próxima acción no es Modo 2. El orden estricto es:

1. autorizar y resolver la visibilidad pública;
2. detener/archivar la Gate B inválida;
3. crear `mvp/integracion-modo-1` desde `gate-d/modo-1`;
4. escribir el test integral que demuestra que `main()` no cablea el pipeline;
5. corregir servicios/puertos sanos y persistencia por tipo;
6. cablear Modo 1 desde configuración;
7. completar la ventana +1 minuto y el contrato real del proveedor;
8. sanear identificadores y excepciones;
9. validar instalación, Cloudflare, cuatro incidentes y 24 horas reales;
10. fusionar el primer PR a `main`;
11. recién entonces comenzar #199.

Saltarse los pasos 4–9 produciría un `main` con muchos módulos y un servicio que
parece activo, pero que no diagnostica incidentes: exactamente el estado que esta
auditoría encontró en Gate D.

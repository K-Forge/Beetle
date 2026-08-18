# Doctor J/K — Beetle
## Roadmap del Proyecto
**Versión 4.0 — Agosto 2026**  
**Duración total:** 10 semanas | **55 tareas** en alcance obligatorio

---

## Resumen ejecutivo

| Métrica | Valor |
|---------|-------|
| **Fases** | 11 (0–10) |
| **Semanas** | 10 totales |
| **Tareas** | 55 obligatorias + 1 opcional |
| **Ruta crítica** | Fase 0 → 1 → 2 (bloquea todas las demás) |
| **Riesgo mayor** | Fase 2 — Detector (2 semanas, 80% del riesgo técnico) |
| **Riesgo secundario** | Fase 9 — Modo 3 obligatorio, 9 tareas en 1 semana |
| **Paralelizable** | Fase 5 — Prompt (desde semana 3 con evidencia simulada) |

### Qué cambió frente a la v3.0

| Cambio | Impacto en el roadmap |
|--------|----------------------|
| **Modo 3 pasa a obligatorio** | Fase 9 deja de ser "opcionales" y pasa a ser el Remediador Automático con sus 5 salvaguardas. +8 tareas |
| **Sanitización de datos sensibles** | Nueva pieza en el pipeline entre recolección y LLM. +2 tareas en Fase 3 |
| **Se elimina el modo Ollama local** | −1 tarea. El criterio de Fase 4 pasa de 3 proveedores a 2 |
| **Producto comercial de código cerrado** | Repo privado desde Fase 0; empaquetado para distribución en Fase 10 |
| **Cliente objetivo definido (PyME)** | La instalación en <15 min pasa a ser criterio de avance, no aspiración |

---

## Fase 0 — Preparación
**Duración:** 2 días | **Semana:** 1  
**Área:** Infraestructura | **Dependencias:** Ninguna

Establecer el entorno de desarrollo y cuentas en la nube.

| # | Tarea | Detalle |
|---|-------|--------|
| 1 | Crear repositorio privado en GitHub | Estructura de carpetas completa, `.gitignore`, README base. **Privado** — el producto es de código cerrado |
| 2 | Configurar VPS Oracle Always Free | Ubuntu Server 24.04 ARM64, Ampere A1 (hasta 4 OCPU / 24 GB RAM / 200 GB). Dar acceso SSH a los miembros del equipo |
| 3 | Snapshot de VPS limpio | Boot volume backup en Oracle para restaurar después de pruebas destructivas |
| 4 | Instalar carga realista | Nginx + PostgreSQL (~50k filas) + app pequeña + cron job |
| 5 | Configurar Cloudflare | Account ID + token Workers AI en `.env` |

**Criterio de avance:** VPS listo con carga realista, Cloudflare token funcional.

---

## Fase 1 — Monitor + Trigger
**Duración:** 3 días | **Semana:** 1  
**Área:** Detección | **Dependencias:** Fase 0

Implementar la vigilancia pasiva y los disparadores de tiempo real.

| # | Tarea | Detalle |
|---|-------|--------|
| 6 | Monitor con polling | Script Python que cada 30s revisa: servicios (systemctl), disco (df), memoria (free), puertos (ss), carga (uptime) |
| 7 | Trigger bash en tiempo real | Script que escucha `journalctl -f` filtrado por errores y dispara el agente inmediatamente |
| 8 | Normalizar señales | Convertir salidas a diccionario único: `{timestamp, signal_type, value, threshold, crossed}` |

**Criterio de avance:** Script corre 1+ hora sin errores, lecturas coherentes y reproducibles.

---

## Fase 2 — Detector ⚠️ RUTA CRÍTICA
**Duración:** 2 semanas | **Semanas:** 2–3  
**Área:** Detección | **Dependencias:** Fase 1  
**Criticidad:** Bloquea todo lo demás

La lógica que distingue un incidente real de un pico normal. Esta es la fase más riesgosa técnicamente.

| # | Tarea | Detalle |
|---|-------|--------|
| 9 | Contadores de persistencia | Cada señal lleva contador: se confirma incidente solo si persiste N ciclos (ej: 2+ ciclos = incidente) |
| 10 | Umbrales configurables | Archivo `config.toml`: disco >90%, memoria <10% disponible, puerto no escucha >60s, etc. |
| 11 | Máquina de estados | Transiciones: normal → candidato → incidente → resuelto. Rechaza picos de <N segundos |
| 12 | Deduplicación | Un incidente activo no re-dispara hasta que se resuelve completamente |
| 13 | Registro de decisiones | Log de por qué disparó/no disparó, con timestamps y evidencia breve |

**Criterio de avance:**
- ✓ Detecta los 4 escenarios básicos (servicio caído, disco lleno, memoria agotada, puerto ocupado)
- ✓ No dispara falsas alarmas durante 24h de operación normal con tráfico
- ✓ No confunde picos temporales (apt upgrade, tráfico) con incidentes

**⚠️ Nota:** Si esta fase se atrasa, recortar los opcionales de Fase 10, nunca las salvaguardas de Fase 9.

---

## Fase 3 — Recolector + Sanitización
**Duración:** 5 días | **Semana:** 4  
**Área:** Recolección + LLM | **Dependencias:** Fase 2

Armar la ventana de evidencia y enmascarar los datos sensibles antes de que salgan del servidor.

| # | Tarea | Detalle |
|---|-------|--------|
| 14 | Recorte de ventana temporal | Cuando dispara en t=0, recolectar logs desde t=-5min hasta t=+1min |
| 15 | Filtrado por prioridad | Reducir volumen: solo `warning` y superior; descartar `info` y `debug` |
| 16 | Ensamblado de evidencia | Bloque estructurado: metadatos (hostname, timestamp) + logs + snapshot (servicios, disco, puertos) + cambios recientes (paquetes, configs) + historial de incidentes anteriores |
| 17 | Truncado inteligente | Si supera ~10k tokens, cortar logs más antiguos manteniendo la sección de error |
| 18 | Guardar evidencia cruda | Junto a cada informe, guardar `evidencia.txt` sin sanitizar (para debug e inspección local) |
| 19 | **Módulo sanitizador** | `sanitizador.py` entre recolector y cliente LLM. Regex para: IPs → `[IP_1]`, variables PASSWORD/SECRET/KEY/TOKEN → `[REDACTADO]`, Bearer/JWT → `[TOKEN_REDACTADO]`, `/home/usuario/` → `/home/[USUARIO]/`, claves SSH → `[REDACTADO]` |
| 20 | **Pruebas del sanitizador** | Verificar consistencia del reemplazo dentro de un mismo informe (la misma IP siempre es `[IP_1]`), casos límite, y documentar honestamente qué NO cubre |

**Criterio de avance:** Evidencia entra al modelo en <30 segundos, tamaño <12k tokens, formato consistente, y ninguna IP/credencial/ruta de usuario sale sin enmascarar en los escenarios de prueba.

**Nota honesta:** La sanitización por patrones no es exhaustiva. Cubre los casos comunes y verificables; un dato con formato inesperado puede escaparse. Documentarlo, no sobrevenderlo.

---

## Fase 4 — Cliente LLM
**Duración:** 2 días | **Semana:** 4  
**Área:** Recolección + LLM | **Dependencias:** Fase 2

Cliente HTTP robusto que habla con el proveedor de IA.

| # | Tarea | Detalle |
|---|-------|--------|
| 21 | Cliente OpenAI-compatible | POST a `/v1/chat/completions` con headers, auth, retry logic |
| 22 | Manejo de errores | Timeouts (30s→abortar), rate limits (backoff 1s→2s→4s), respuestas vacías (reintentar hasta 3x) |
| 23 | Reintentos con backoff | Exponencial: 1s → 2s → 4s. Máx 3 intentos. |
| 24 | Modo caché | Flag de desarrollo que reutiliza respuestas anteriores en lugar de llamar API (no gastar tokens) |
| 25 | Fallback sin LLM | Si el modelo no responde, generar informe mínimo con la evidencia cruda etiquetada |

**Criterio de avance:** Llama a Cloudflare (gpt-oss-120b, gratis) y DeepSeek (V4 Flash) indistintamente con solo cambiar variables de entorno.

**⚠️ Cambio v4.0:** Ya no hay tercer backend. Se eliminó el modo Ollama local por alcance y foco de producto — no porque fuera técnicamente inviable. La mitigación ante cambios de proveedor es más débil que en v3.0 y así queda documentada.

---

## Fase 5 — Prompt
**Duración:** 1 semana | **Semana:** 5 (paralelizable desde semana 3)  
**Área:** Prompt + Informes | **Dependencias:** Fase 2 (puede trabajarse con evidencia simulada)  
**Nota:** ⚡ **PARALELIZABLE** — no esperar a que fase 2 esté 100% lista

Diseñar y refinar el prompt del diagnosticador.

| # | Tarea | Detalle |
|---|-------|--------|
| 26 | Prompt estructurado | Rol + restricciones + estructura: diagnóstico (qué/cuándo/causa raíz/descartado) + guía (confirmar/resolver paso a paso/verificar/prevenir) |
| 27 | Iteración con escenarios | Probar prompt contra evidencia guardada de cada escenario. Ajustar redacción, nivel de confianza, reducir jerga |
| 28 | Validar comprensibilidad del lenguaje | Revisión interna e iterativa: ¿se entiende sin experiencia en sysadmin? (la prueba formal con usuarios es la tarea 50) |
| 29 | Reducir alucinaciones | Agregar secciones "Descartado" (causas consideradas y por qué NO encajan), marcar confianza (alta/media/baja) en cada hipótesis |

**Criterio de avance:** El prompt razona igual sobre evidencia sanitizada (`[IP_1]`) que sobre la cruda — la correlación entre eventos se mantiene.

---

## Fase 6 — Persistencia y Servicio Systemd
**Duración:** 3 días | **Semana:** 6  
**Área:** Prompt + Informes | **Dependencias:** Fase 4

Hacer que el agente viva como un servicio permanente.

| # | Tarea | Detalle |
|---|-------|--------|
| 30 | Escritura de informes | Ruta: `/var/lib/doctorjk/informes/` con nombre `{timestamp}_{incident_type}.md` |
| 31 | Unit systemd | `doctorjk.service` con `Restart=always`, `User=doctorjk`, logs a journald |
| 32 | Script de instalación | `install.sh` que crea usuarios, directorios, dependencias, copia archivos, habilita servicio. **Meta dura: <15 minutos de principio a fin** |
| 33 | Rotación de informes | No llenar disco: guardar últimos 30 informes, borrar más antiguos. O por fecha (>30 días) |

**Criterio de avance:** `systemctl start doctorjk` inicia el agente. Instalación completa cronometrada en <15 min sobre VPS limpio.

---

## Fase 7 — Remediador por Scripts (Modo 2)
**Duración:** 1 semana | **Semana:** 7  
**Área:** Prompt + Informes | **Dependencias:** Fase 6

Ejecutar correcciones predefinidas y deterministas.

| # | Tarea | Detalle |
|---|-------|--------|
| 34 | Scripts de corrección | Bash scripts probados: `fix_disco.sh`, `fix_servicio.sh`, `fix_memoria.sh`, `fix_puerto.sh` |
| 35 | Clasificador de tipo | Mapea el tipo de incidente detectado → script correcto. Ej: `incidente_disco` → `fix_disco.sh` |
| 36 | Logging de auditoría | Registrar: qué comando se ejecutó, timestamps, código de salida, stdout/stderr |
| 37 | Verificación post-corrección | Ejecutar comando de verificación (ej: `systemctl status`) después de la corrección. Si falla → revertir o reportar |

**Criterio de avance:** Un incidente de disco lleno se resuelve automáticamente en <2 minutos sin intervención humana.

---

## Fase 8 — Escenarios de Prueba y Medición
**Duración:** 1 semana | **Semana:** 8  
**Área:** Pruebas | **Dependencias:** Fases 2–7 completas

Ejecución controlada de todos los casos de prueba y tabulación de métricas.

| # | Tarea | Detalle |
|---|-------|--------|
| 38 | Scripts de provocación | 9 escenarios: 4 básicos (servicio caído, disco, memoria, puerto) + 5 realistas (cascada, fuga memoria, config rota, etc.) |
| 39 | Respuestas esperadas | Documentar antes de correr: qué síntoma debe observarse, causa raíz correcta, pasos de solución correctos |
| 40 | 3 corridas por escenario | 9 × 3 = 27 ejecuciones + 5 casos negativos × 3 = 15 ejecuciones = **42 corridas totales** |
| 41 | Tabulación de resultados | Matriz: escenario × métrica. Calcular % de éxito en cada métrica |

**Métricas de éxito:**
- Tasa de detección: >90%
- Precisión de causa raíz: >80%
- Tasa de falsos positivos: <10%
- Tiempo a informe: <120s
- Utilidad de la guía: >70%
- Comprensibilidad: >80%

**Criterio de avance:** Todas las métricas obligatorias dentro de meta.

---

## Fase 9 — Remediador Automático (Modo 3) ⚠️ ALCANCE OBLIGATORIO
**Duración:** 1 semana | **Semana:** 9  
**Área:** Prompt + Informes / Pruebas | **Dependencias:** Fases 2–8

**Cambio central de la v4.0.** El Modo 3 dejó de ser "fase beta si sobra tiempo": es un diferenciador comercial central del producto. Las salvaguardas de la sección 14.5 del documento de proyecto son **innegociables** — cada una es una tarea propia porque ninguna puede quedarse a medias.

| # | Tarea | Detalle |
|---|-------|--------|
| 42 | Generador de plan de corrección | El modelo devuelve un plan estructurado: por cada paso, comando exacto + resultado esperado + condición para continuar + condición para abortar |
| 43 | **[SALVAGUARDA]** Lista blanca de comandos | Solo se ejecutan patrones validados (reiniciar servicio, borrar logs en rutas específicas, liberar espacio en directorios predefinidos). Nunca comandos genéricos generados libremente |
| 44 | **[SALVAGUARDA]** Modo `--dry-run` | Muestra qué haría sin ejecutar nada. Obligatorio durante desarrollo y demo |
| 45 | **[SALVAGUARDA]** Flag explícito `--auto-fix` | El remediador solo se activa con flag o configuración explícita. Por defecto, Doctor J/K solo diagnostica (Modo 1) |
| 46 | Ejecutor paso a paso con validación | Ejecuta cada paso del plan, captura resultado, valida contra la condición esperada antes de continuar |
| 47 | **[SALVAGUARDA]** Aborto automático y escalamiento | Si cualquier paso produce un resultado inesperado, el remediador se detiene, notifica, deja el informe y NO sigue |
| 48 | **[SALVAGUARDA]** Logging de auditoría del Modo 3 | Cada comando ejecutado, su resultado y la decisión del modelo quedan en el informe final y en journald |
| 49 | Medición de corrección automática | Métrica obligatoria (ya no condicional): remediaciones exitosas **>85%** |
| 50 | Prueba de comprensibilidad con usuarios | 5 informes generados a 3–5 personas no técnicas. ¿Entienden qué pasó? ¿Podrían seguir los pasos? Registrar retroalimentación |

**Criterio de avance:** Corrección automática >85%, comprensibilidad >80%, y las 5 salvaguardas implementadas y verificadas.

**⚠️ Riesgo de cronograma:** 9 tareas en una semana. Incluir el Modo 3 en el alcance obligatorio aumenta la carga de esta fase y reduce el margen de maniobra si la Fase 2 se atrasa. Si hay que recortar, se recortan los opcionales de Fase 10 — **nunca las salvaguardas (tareas 43, 44, 45, 47 y 48)**.

---

## Fase 10 — Documentación y Entrega
**Duración:** 1 semana | **Semana:** 10  
**Área:** Soporte | **Dependencias:** Todas

Pulir la presentación, empaquetar el producto y documentar todo.

| # | Tarea | Detalle |
|---|-------|--------|
| 51 | Documentación de arquitectura | `docs/arquitectura.md`: diagramas, decisiones de diseño, justificación de cada componente |
| 52 | README completo | Instalación, configuración, uso, troubleshooting. Incluye la lista blanca de comandos documentada públicamente (transparencia operativa) |
| 53 | Empaquetado para distribución | Paquete instalable o imagen Docker. El producto se distribuye compilado, no como código fuente |
| 54 | Preparación de demo | Scripts de demostración + informes pregenerados de respaldo. **Ya no hay modo offline** — los informes pregenerados son el único respaldo si falla la red |
| 55 | Presentación | Problem statement, cliente objetivo (PyME), solución, resultados de pruebas, modelo de producto y roadmap futuro |
| 56 | **[OPT]** Backend + panel web | Cloudflare Workers + D1 para recibir informes de múltiples servidores. Panel con historial. Primero en recortarse si hay atraso |

**Criterio de avance:** Alguien externo puede leer el README, instalar en <15 min y entender qué hace el agente sin ver el código.

---

## Dependencias y Ruta Crítica

```
Semana:     1     2     3     4     5     6     7     8     9    10
            |-----|-----|-----|-----|-----|-----|-----|-----|-----|
Fase 0:     ■■
Fase 1:       ■■■
Fase 2:         ■■■■■■■■■■■■■ (CRÍTICA — bloquea todas)
Fase 3:                     ■■■■■
Fase 4:                     ■■
Fase 5:                 ■■■■■■■ (puede ser en paralelo)
Fase 6:                         ■■■
Fase 7:                             ■■■■■■■
Fase 8:                                   ■■■■■■■
Fase 9:                                         ■■■■■■■ (OBLIGATORIA)
Fase 10:                                              ■■■■■■■
```

### Puntos críticos

1. **Fase 2 no se puede adelantar.** Es la más arriesgada (80% del riesgo técnico). Si se atrasa, el impacto ahora es mayor que en la v3.0: antes se recortaba la Fase 9 entera (era opcional), hoy la Fase 9 es alcance obligatorio.

2. **Fase 9 es el nuevo cuello de botella.** 9 tareas en una semana, incluidas 5 salvaguardas innegociables. Es la consecuencia directa de mover el Modo 3 al alcance obligatorio.

3. **Fase 5 es la única paralelizable.** Puede trabajarse desde la semana 3 con evidencia simulada.

4. **Las fases 3, 4, 6, 7 dependen directamente de Fase 2.**

5. **Fase 8 requiere las fases 2–7 completas.** Es la validación previa al Modo 3.

### Orden de recorte si hay atraso

| Prioridad de recorte | Qué se recorta |
|---|---|
| 1º | Tarea 56 — Backend + panel web (opcional) |
| 2º | Tarea 53 — Empaquetado (se entrega como script de instalación) |
| 3º | Alcance de escenarios en Fase 8 (de 3 corridas a 2 por escenario) |
| **Nunca** | Salvaguardas (tareas 43, 44, 45, 47 y 48), ni las fases 2, 7 u 8 |

---

## Recursos por Fase

| Fase | Lenguaje | Stack | Herramientas |
|------|----------|-------|-------------|
| 0 | Bash | VPS Oracle + GitHub (privado) + Cloudflare | Oracle Cloud Console |
| 1 | Python 3.11+ | systemd + journalctl + bash | Linux tools (native) |
| 2 | Python 3.11+ | logging + diccionarios + estado | VS Code + pytest |
| 3 | Python 3.11+ | subprocess + `re` (regex) | bash + pytest |
| 4 | Python 3.11+ | requests / httpx | Cloudflare / DeepSeek |
| 5 | Markdown | Prompt engineering | Text editor |
| 6 | Python + Bash | systemd + paths | Linux |
| 7 | Bash | Scripts de corrección | sed + systemctl |
| 8 | Python + Bash | Orquestación de pruebas | Snapshots + scripts |
| 9 | Python + Bash | Ejecución validada + auditoría | Snapshots + personas (no técnicas) |
| 10 | Markdown + Docker | Documentación + empaquetado | GitHub + diagrams |

---

## Criterios de Éxito por Fase

| Fase | Criterio | Validación |
|------|----------|-----------|
| 0 | VPS listo con carga realista | Nginx + Postgres responden, Cloudflare token funcional |
| 1 | Monitor corre 1+ hora sin errores | Lecturas coherentes y logs limpios |
| 2 | **Detecta 4 básicos, 0 falsos en 24h** | 4/4 escenarios, 0 disparos en operación normal |
| 3 | Evidencia <12k tokens, <30s, sanitizada | Ninguna IP/credencial sin enmascarar en los escenarios de prueba |
| 4 | Llama 2 proveedores indistintamente | Cambio de env var = cambio de backend |
| 5 | Diagnóstico no se degrada con datos enmascarados | El modelo correlaciona igual sobre `[IP_1]` que sobre la IP real |
| 6 | Instalación en <15 min | Cronometrada sobre VPS limpio |
| 7 | Incidente resuelto <2 min automáticamente | Script ejecuta, verificación pasa |
| 8 | Todas las métricas en meta | >90% detección, >80% causa raíz, <10% falsos |
| 9 | **Corrección automática >85% + comprensibilidad >80% + 5 salvaguardas** | Remediaciones exitosas, dry-run funcional, aborto verificado |
| 10 | Producto instalable y documentado | Alguien externo instala en <15 min sin ver el código |

---

## Estimación de Esfuerzo

| Área | Semanas | % del total | Riesgo |
|------|---------|-----------|--------|
| Detección (Fases 1–2) | 2.5 | 25% | 🔴 Alto |
| Recolección + Sanitización + LLM (Fases 3–4) | 1.5 | 15% | 🟡 Medio |
| Prompt + Informes + Remediación Modo 2 (Fases 5–7) | 2.5 | 25% | 🟡 Medio |
| Pruebas (Fase 8) | 1 | 10% | 🟢 Bajo |
| Remediador Automático Modo 3 (Fase 9) | 1 | 10% | 🔴 Alto |
| Documentación y entrega (Fase 10) | 1 | 10% | 🟢 Bajo |
| Setup inicial (Fase 0) | 0.5 | 5% | 🟢 Bajo |

---

## Notas para el equipo

- **Comunicación:** Reunión de standup diaria (15min) para detectar bloqueos en ruta crítica.
- **Testing:** Cada fase tiene snapshots del VPS (boot volume backups en Oracle) para rollback rápido.
- **Documentación:** Llenar wiki del repo conforme avanza, no al final.
- **Repositorio privado:** El código no se publica. Si se arma un showcase para portafolio, va documentación, arquitectura, capturas e informes de ejemplo — nunca el código fuente del agente.
- **Demo:** Grabado + vivo. Si falla la red, informes pregenerados (único respaldo desde que se eliminó el modo local).
- **Presupuesto IA:** $0–$1.16 en 6 meses. En producción el costo de inferencia lo asume Beetle, no el cliente.
- **Riesgo de VPS compartido:** todo el equipo desarrolla sobre un único VPS Oracle Always Free (propiedad de Brian). Si se pierde (Oracle reclama la instancia, error de configuración, cuenta comprometida), el equipo pierde el entorno de desarrollo completo. Mitigación: snapshots frecuentes (al menos antes de cada fase) y que cada miembro tenga su propia cuenta Oracle Always Free como respaldo (ver sección 18 del documento de proyecto).

---

**Versión:** 4.0  
**Actualizado:** Agosto 2026  
**Autor:** Equipo Beetle

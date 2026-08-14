# `pruebas/` — verificación y medición

Aquí vive la evidencia de que el producto funciona. Dos cosas distintas conviven en esta carpeta:
las **pruebas automáticas** del código (pytest) y la **medición del producto** contra las metas
de la sección 16 — que no se automatiza porque parte de ella la juzgan personas.

## Estructura recomendada

```
pruebas/
├── unitarias/            # pytest — ver su propio README
├── esperados/            # causa raíz definida ANTES de cada corrida
├── resultados/           # informes generados + matriz de resultados
└── comprensibilidad/     # retroalimentación de personas no expertas
```

## Las metas que se miden aquí

| Métrica | Definición | Meta | Dónde se registra |
|---|---|---|---|
| Tasa de detección | Detectados / provocados | > 90% | `resultados/` |
| Precisión de causa raíz | Informes con causa correcta | > 80% | `esperados/` vs `resultados/` |
| Falsos positivos | Disparos en escenarios negativos | < 10% | `resultados/` |
| Tiempo a informe | Del fallo al archivo escrito | < 120 s | `resultados/` |
| Utilidad de la guía | Guías que resuelven el problema | > 70% | `resultados/` |
| Comprensibilidad | No expertos que entienden | > 80% | `comprensibilidad/` |
| Corrección automática | Remediaciones exitosas | > 85% | `resultados/` |

## Protocolo

42 corridas controladas: 9 escenarios × 3 + 5 negativos × 3. Todas con tráfico de fondo.

La regla que hace válida la medición: **la causa raíz se escribe en `esperados/` antes de correr
el escenario**. Si se escribe después de leer el informe, la evaluación deja de ser honesta —
siempre parece que el modelo acertó.

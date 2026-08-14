# `pruebas/comprensibilidad/` — la prueba que no se automatiza

Retroalimentación de personas que **no** administran servidores, leyendo informes reales del
agente. Meta: que más del 80% entienda qué pasó (§16).

Es la prueba que decide si el producto cumple su promesa. Un informe técnicamente correcto que
nadie entiende no reduce el MTTR de nadie: el cliente objetivo es un CTO que apaga incendios de
madrugada, no un especialista en Postgres.

## Estructura recomendada

```
comprensibilidad/
├── guion_entrevista.md           # las mismas preguntas para todos
├── informes_evaluados/           # los 5 informes que se muestran
│   ├── A_disco_lleno.md
│   └── B_cascada.md
└── respuestas/
    ├── persona_1.md
    └── persona_2.md
```

## Protocolo

5 informes, 3–5 personas que no son administradoras de sistemas. A cada una se le muestra el
informe sin contexto adicional y se le pregunta:

1. ¿Qué pasó en el servidor? (con sus palabras)
2. ¿Por qué pasó?
3. ¿Podrías seguir los pasos de la guía? ¿Dónde te trabarías?
4. ¿Qué palabra o frase no entendiste?
5. Del 1 al 5, ¿qué tan seguro te sentirías aplicando esto?

La pregunta 4 es la más útil: cada término que se repite como no entendido es una corrección
concreta al prompt.

## Convenciones

- Se registra la respuesta literal, no un resumen interpretado.
- Se anota el perfil de la persona (¿usa terminal? ¿qué tanto?) sin datos personales.
- Cada hallazgo que llega al prompt se anota con la fecha, para poder ligarlo a la tanda de
  `resultados/` que vino después.

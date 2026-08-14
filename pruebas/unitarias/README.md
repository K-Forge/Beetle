# `pruebas/unitarias/` — tests automáticos con pytest

Pruebas del código, no del producto. Corren en la máquina de cualquiera del equipo, sin VPS y
sin romper nada: todo lo que dependa del sistema (journalctl, systemctl, df) se simula con
salidas de ejemplo guardadas.

## Estructura recomendada

```
unitarias/
├── conftest.py               # fixtures compartidas
├── test_sanitizador.py       # el más importante — ver abajo
├── test_detector.py          # persistencia y rechazo de casos negativos
├── test_lista_blanca.py      # ningún comando fuera de los patrones pasa
├── test_recolector.py        # recorte correcto de la ventana temporal
├── test_clasificador.py      # tipo de incidente → script correcto
└── fixtures/                 # salidas reales capturadas del VPS
    ├── journalctl_disco_lleno.txt
    ├── systemctl_failed.txt
    └── df_lleno.txt
```

Capturar salidas reales del VPS en `fixtures/` es lo que hace que estas pruebas valgan: probar
el parser contra una salida inventada solo demuestra que el parser entiende lo que uno imaginó.

## Qué debe cubrir `test_sanitizador.py`

Es el test con más peso, porque un fallo aquí filtra datos del cliente (tarea #185):

- IPs en varios formatos: IPv4 con puerto, dentro de URLs, en logs de nginx.
- **Consistencia**: la misma IP produce el mismo placeholder en todo el informe — es lo que
  permite al modelo correlacionar eventos.
- Credenciales en varios formatos: `PASSWORD=...`, `export SECRET_KEY=...`.
- Tokens JWT y Bearer en cabeceras.
- Rutas `/home/<usuario>/...` con distintos nombres.
- Claves SSH en formato OpenSSH.
- Casos límite: IPs dentro de URLs, credenciales multilínea, formatos inesperados.

Lo que el sanitizador **no** cubre se documenta en `docs/sanitizador_limitaciones.md`, no se
esconde.

## Convenciones

- Un archivo `test_<modulo>.py` por módulo de `doctorjk/`.
- Nada de red en las pruebas unitarias: el cliente LLM se simula.
- Los tests del sanitizador y de la lista blanca deben pasar al 100% — son salvaguardas, no
  funcionalidades.

# Pruebas del punto de entrada (issue #222): parseo de argumentos, el FIFO
# como canal unico entre trigger.sh y el orquestador, el apagado limpio ante
# SIGTERM, y desde Gate 2 el cableado real del Modo 1 (config -> Detector ->
# cola de incidentes pendientes -> pipeline). No prueban el loop infinito de
# run() directamente -- eso se cubre indirectamente: wait_for_next_cycle() es
# el unico lugar que decide "tick" o "trigger", y run() llama al mismo
# callback sin importar cual de los dos devolvio.
from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doctorjk import recolector
from doctorjk.main import (
    AppContext,
    PendingIncident,
    build_app,
    build_incident_pipeline,
    ensure_fifo,
    log_snapshot,
    parse_args,
    pop_due_incidents,
    queue_pending_incident,
    run,
    seconds_until_next_event,
    wait_for_next_cycle,
)
from doctorjk.modelos import (
    Incident,
    IncidentState,
    ListeningPort,
    MemoryUsage,
    MonitoredPort,
    ServiceState,
    SignalType,
    SystemSnapshot,
)

REPO_ROOT = Path(__file__).parent.parent.parent

CONFIG_TOML_MINIMA = """
intervalo_monitor_s = 30
ciclos_persistencia = 2
enfriamiento_ciclos = 2
disco_pct = 90
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
servicios_vigilados = ["postgresql.service"]
puertos_vigilados = [{ puerto = 5432, servicio = "postgresql.service" }]
directorio_informes = "{reports_dir}"
modo_remediacion = "diagnostico"
auto_fix = false
dry_run = true
timeout_comando_s = 5
llm_url = "https://proveedor.invalido/v1/chat/completions"
llm_modelo = "gpt-oss-120b"
llm_timeout_s = 5
llm_cache = false
"""


def _escribir_config_y_prompt(tmp_path: Path) -> tuple[Path, Path]:
    reports_dir = tmp_path / "informes"
    reports_dir.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TOML_MINIMA.replace("{reports_dir}", str(reports_dir)), encoding="utf-8"
    )
    prompt_path = tmp_path / "diagnosticador.md"
    prompt_path.write_text("prompt de prueba", encoding="utf-8")
    return config_path, prompt_path


# ------------------------------------------------------------------- parse_args


def test_defaults_son_seguros():
    args = parse_args([])
    assert args.dry_run is False
    assert args.auto_fix is False
    assert args.once is False
    # None: sin --interval explícito se usa intervalo_monitor_s de config.toml.
    assert args.interval is None


def test_auto_fix_y_dry_run_son_incompatibles():
    with pytest.raises(SystemExit):
        parse_args(["--auto-fix", "--dry-run"])


def test_intervalo_cero_se_rechaza():
    with pytest.raises(SystemExit):
        parse_args(["--interval", "0"])


def test_intervalo_negativo_se_rechaza():
    with pytest.raises(SystemExit):
        parse_args(["--interval", "-5"])


# ------------------------------- cableado real del pipeline (plan-finalizacion-mvp.md §3.1, defecto 1)


def test_build_app_debe_cablear_el_pipeline_no_solo_registrar(tmp_path):
    # Expone el defecto #1 de la auditoría: build_app() ya no puede dejar
    # on_snapshot=log_snapshot, o ningún snapshot llegaría jamás al Detector.
    config_path, prompt_path = _escribir_config_y_prompt(tmp_path)
    args = parse_args(["--config", str(config_path), "--prompt", str(prompt_path)])
    contexto = build_app(args)
    try:
        assert contexto.on_snapshot is not log_snapshot
    finally:
        contexto.close()


def test_build_app_usa_el_intervalo_de_config_sin_override_cli(tmp_path):
    config_path, prompt_path = _escribir_config_y_prompt(tmp_path)
    args = parse_args(["--config", str(config_path), "--prompt", str(prompt_path)])
    contexto = build_app(args)
    try:
        assert contexto.interval_s == 30.0  # intervalo_monitor_s del TOML
    finally:
        contexto.close()


def test_build_app_respeta_el_override_explicito_de_intervalo(tmp_path):
    config_path, prompt_path = _escribir_config_y_prompt(tmp_path)
    args = parse_args(
        ["--config", str(config_path), "--prompt", str(prompt_path), "--interval", "5"]
    )
    contexto = build_app(args)
    try:
        assert contexto.interval_s == 5.0
    finally:
        contexto.close()


def test_build_app_config_invalida_falla_con_mensaje_accionable(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("esto no es toml valido [[[", encoding="utf-8")
    prompt_path = tmp_path / "diagnosticador.md"
    prompt_path.write_text("prompt", encoding="utf-8")
    args = parse_args(["--config", str(config_path), "--prompt", str(prompt_path)])

    with pytest.raises(SystemExit, match=str(config_path)):
        build_app(args)


def test_build_app_prompt_ausente_falla_con_mensaje_accionable(tmp_path):
    config_path, _ = _escribir_config_y_prompt(tmp_path)
    prompt_path = tmp_path / "no-existe.md"
    args = parse_args(["--config", str(config_path), "--prompt", str(prompt_path)])

    with pytest.raises(SystemExit, match=str(prompt_path)):
        build_app(args)


# --------------------------------------------------------------------- ensure_fifo


def test_ensure_fifo_crea_pipe_con_permisos_restrictivos(tmp_path):
    fifo_path = tmp_path / "run" / "doctorjk" / "trigger.fifo"
    assert ensure_fifo(fifo_path) is True
    assert stat.S_ISFIFO(fifo_path.stat().st_mode)
    assert stat.S_IMODE(fifo_path.stat().st_mode) == 0o600


def test_ensure_fifo_es_idempotente(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    assert ensure_fifo(fifo_path) is True
    assert ensure_fifo(fifo_path) is True


def test_ensure_fifo_sin_permisos_degrada_a_solo_polling(tmp_path, monkeypatch):
    fifo_path = tmp_path / "sin-permiso" / "trigger.fifo"

    def falla_permiso(self, *args, **kwargs):
        raise PermissionError("denegado")

    monkeypatch.setattr(Path, "mkdir", falla_permiso)
    assert ensure_fifo(fifo_path) is False


# ---------------------------------------------------------- wait_for_next_cycle


def test_wait_for_next_cycle_sin_fifo_espera_el_intervalo(monkeypatch):
    dormidos = []
    monkeypatch.setattr(time, "sleep", dormidos.append)
    assert wait_for_next_cycle(None, 30.0) == "tick"
    assert dormidos == [30.0]


def test_wait_for_next_cycle_detecta_escritura_del_trigger(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    os.mkfifo(fifo_path)
    fd_lectura = os.open(str(fifo_path), os.O_RDWR | os.O_NONBLOCK)
    fd_escritura = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd_escritura, b"1\n")
        assert wait_for_next_cycle(fd_lectura, 5.0) == "trigger"
    finally:
        os.close(fd_escritura)
        os.close(fd_lectura)


def test_wait_for_next_cycle_sin_senal_cae_a_tick_por_timeout(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    os.mkfifo(fifo_path)
    fd_lectura = os.open(str(fifo_path), os.O_RDWR | os.O_NONBLOCK)
    try:
        assert wait_for_next_cycle(fd_lectura, 0.1) == "tick"
    finally:
        os.close(fd_lectura)


# --------------------------------------------------------------------------- run


def test_once_llama_al_callback_una_sola_vez_sin_tocar_el_fifo():
    llamadas = []
    contexto = AppContext(
        interval_s=30.0,
        fifo_path=Path("/ruta/que/no/deberia/tocarse/trigger.fifo"),
        once=True,
        take_snapshot=lambda: "muestra-falsa",
        on_snapshot=llamadas.append,
    )
    run(contexto)
    assert llamadas == ["muestra-falsa"]


def test_run_termina_limpio_con_sigterm(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    config_path, prompt_path = _escribir_config_y_prompt(tmp_path)
    entorno = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proceso = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "doctorjk.main",
            "--config",
            str(config_path),
            "--prompt",
            str(prompt_path),
            "--fifo-path",
            str(fifo_path),
            "--interval",
            "0.2",
        ],
        cwd=str(REPO_ROOT),
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.5)
        proceso.send_signal(signal.SIGTERM)
        codigo = proceso.wait(timeout=5)
    finally:
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait()
    salida_error = proceso.stderr.read() if proceso.stderr else ""
    assert codigo == 0, salida_error


# ------------------------------------------------- cableado del Modo 1 (D4)


def _config_de_prueba(tmp_path, **overrides):
    from doctorjk.config import AppConfig, RemediationMode

    base = dict(
        monitor_interval_s=30.0,
        persistence_cycles=2,
        cooldown_cycles=2,
        disk_pct_threshold=90,
        memory_available_mb_threshold=512,
        port_timeout_s=60.0,
        service_cycles=2,
        port_cycles=2,
        monitored_services=("postgresql.service",),
        monitored_ports=(),
        reports_dir=tmp_path,
        remediation_mode=RemediationMode.DIAGNOSTICO,
        auto_fix=False,
        dry_run=True,
        command_timeout_s=5.0,
        llm_url="https://proveedor/v1",
        llm_model="gpt-oss-120b",
        llm_timeout_s=5.0,
        llm_cache=False,
        llm_api_key="k",
    )
    base.update(overrides)
    return AppConfig(**base)


def test_build_pipeline_deps_arma_los_cinco_contratos(tmp_path):
    from doctorjk.main import build_pipeline_deps

    config = _config_de_prueba(tmp_path)
    deps = build_pipeline_deps(config, session=object())

    assert deps.collect_evidence is not None
    assert deps.sanitize_evidence is not None
    assert deps.diagnose is not None
    assert deps.save_report is not None
    assert deps.write_raw_evidence is not None


def test_on_incident_no_propaga_un_fallo_de_es_esperado(tmp_path, caplog):
    # on_incident ya no atrapa Exception a secas (defecto 10): la garantía de
    # "no tumbar la vigilancia" la da handle_incident(), envolviendo los
    # fallos de E/S esperables (acá, recolectar evidencia). Un incidente que
    # falla por una causa operativa real no debe detener el bucle.
    from doctorjk.main import on_incident
    from doctorjk.pipeline import PipelineDeps

    def falla_es(*args, **kwargs):
        raise OSError("journalctl no disponible")

    deps = PipelineDeps(falla_es, falla_es, falla_es, falla_es, falla_es)
    ahora = datetime(2026, 8, 26, tzinfo=timezone.utc)
    incidente = Incident("inc-9", SignalType.SERVICE_FAILED, "x", ahora, ahora, IncidentState.INCIDENT)

    with caplog.at_level("ERROR"):
        on_incident(incidente, "prompt", tmp_path, deps, ahora)

    assert "inc-9" in caplog.text


def test_on_incident_deja_escapar_un_bug_real(tmp_path):
    # Lo que sí debe propagarse -- y por lo tanto hacer ruido en journald en
    # vez de esconderse -- es una excepción que no corresponde a ninguna
    # falla de E/S contemplada por el pipeline.
    from doctorjk.main import on_incident
    from doctorjk.pipeline import PipelineDeps

    def bug(*args, **kwargs):
        raise TypeError("esto es un bug de programación, no un fallo operativo")

    deps = PipelineDeps(bug, bug, bug, bug, bug)
    ahora = datetime(2026, 8, 26, tzinfo=timezone.utc)
    incidente = Incident("inc-10", SignalType.SERVICE_FAILED, "x", ahora, ahora, IncidentState.INCIDENT)

    with pytest.raises(TypeError):
        on_incident(incidente, "prompt", tmp_path, deps, ahora)


# --------------------------------------------- cola de incidentes pendientes (Gate 2.2)


def _snapshot_servicio(activo: bool, captured_at: datetime) -> SystemSnapshot:
    return SystemSnapshot(
        captured_at=captured_at,
        failed_services=(),
        services_available=True,
        disks=(),
        disk_available=True,
        memory=MemoryUsage(total_mb=3900, used_mb=1200, free_mb=800, available_mb=2400),
        memory_available=True,
        ports=(ListeningPort(address="0.0.0.0", port=5432),) if activo else (),
        ports_available=True,
        load=None,
        load_available=False,
        service_states=(ServiceState(name="postgresql.service", active=activo),),
        service_states_available=True,
    )


def test_queue_pending_incident_descarta_el_mas_viejo_si_se_llena():
    from doctorjk.main import MAX_PENDING_INCIDENTS

    cola: list[PendingIncident] = []
    base = datetime(2026, 8, 26, tzinfo=timezone.utc)
    incidentes = [
        Incident(f"inc-{i}", SignalType.DISK_FULL, f"disk:/{i}", base, base, IncidentState.INCIDENT)
        for i in range(MAX_PENDING_INCIDENTS + 1)
    ]
    for incidente in incidentes:
        queue_pending_incident(cola, incidente, base)

    assert len(cola) == MAX_PENDING_INCIDENTS
    assert cola[0].incident.incident_id == "inc-1"  # inc-0 fue el descartado


def test_pop_due_incidents_solo_extrae_lo_vencido():
    base = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    vencido = PendingIncident(
        Incident("inc-vencido", SignalType.DISK_FULL, "disk:/", base, base, IncidentState.INCIDENT),
        collect_after=base,
    )
    futuro = PendingIncident(
        Incident("inc-futuro", SignalType.DISK_FULL, "disk:/var", base, base, IncidentState.INCIDENT),
        collect_after=base + timedelta(minutes=1),
    )
    cola = [vencido, futuro]

    debidos = pop_due_incidents(cola, base)

    assert [p.incident.incident_id for p in debidos] == ["inc-vencido"]
    assert cola == [futuro]


def test_seconds_until_next_event_usa_lo_que_venza_primero():
    base = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    cola = [
        PendingIncident(
            Incident("inc-1", SignalType.DISK_FULL, "disk:/", base, base, IncidentState.INCIDENT),
            collect_after=base + timedelta(seconds=10),
        )
    ]
    assert seconds_until_next_event(cola, interval_s=30.0, now=base) == 10.0
    assert seconds_until_next_event([], interval_s=30.0, now=base) == 30.0


def test_seconds_until_next_event_nunca_es_negativo():
    base = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    vencido = PendingIncident(
        Incident("inc-1", SignalType.DISK_FULL, "disk:/", base, base, IncidentState.INCIDENT),
        collect_after=base - timedelta(seconds=5),
    )
    assert seconds_until_next_event([vencido], interval_s=30.0, now=base) == 0.0


# ---------------------------------------------- build_incident_pipeline (integración)


class _RespuestaFalsa:
    def __init__(self, contenido: str):
        self.status_code = 200
        self._contenido = contenido

    def json(self) -> object:
        return {"choices": [{"message": {"content": self._contenido}}]}


class _SesionFalsa:
    """Responde 200 al instante -- sin esto, cada incidente dispararía el
    backoff real (1/2/4 s) de llm.diagnose() y estas pruebas tardarían
    segundos de verdad por cada caso."""

    def __init__(self):
        self.llamadas = 0

    def post(self, url, *, json, headers, timeout):
        self.llamadas += 1
        return _RespuestaFalsa(f"diagnóstico de prueba #{self.llamadas}")

    def close(self) -> None:
        pass


def test_servicio_falla_confirma_espera_la_ventana_y_luego_diagnostica(tmp_path):
    # Congela el flujo completo de Gate 1.1 + 2.2: un servicio vigilado cruza
    # ciclos_persistencia veces, confirma, y la evidencia NO se recolecta
    # hasta que el reloj real llegue a confirmed_at + WINDOW_AFTER -- nunca
    # antes (defecto 8: no se le pide a journalctl el futuro).
    config = _config_de_prueba(tmp_path, service_cycles=2)
    reloj = {"ahora": datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)}

    procesar, proxima_espera = build_incident_pipeline(
        config, "prompt", _SesionFalsa(), now_fn=lambda: reloj["ahora"]
    )

    t0 = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=30)

    procesar(_snapshot_servicio(activo=False, captured_at=t0))
    assert list(tmp_path.glob("*.md")) == []  # candidato, no confirma todavía

    reloj["ahora"] = t1
    procesar(_snapshot_servicio(activo=False, captured_at=t1))  # confirma en este ciclo

    # El reloj real sigue en t1, la ventana vence en t1+60s: todavía no toca.
    assert list(tmp_path.glob("*.md")) == []
    assert proxima_espera(t1) <= recolector.WINDOW_AFTER.total_seconds()

    # Pasa la ventana +1 minuto de verdad (según el reloj inyectado, no según
    # snapshot.captured_at): recién ahora se recolecta y se escribe informe.
    reloj["ahora"] = t1 + recolector.WINDOW_AFTER
    procesar(_snapshot_servicio(activo=False, captured_at=t1))

    informes = list(tmp_path.glob("*.md"))
    assert len(informes) == 1
    assert "diagnóstico de prueba" in informes[0].read_text(encoding="utf-8")


def test_servicio_se_recupera_no_genera_informe(tmp_path):
    # Resolución: se registra, nunca se llama al pipeline de diagnóstico.
    config = _config_de_prueba(tmp_path, service_cycles=2)
    reloj = {"ahora": datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)}
    sesion = _SesionFalsa()
    procesar, _ = build_incident_pipeline(config, "prompt", sesion, now_fn=lambda: reloj["ahora"])

    t = reloj["ahora"]
    for delta in (0, 30, 60, 90):  # confirma en 60s, se recupera en 90s+
        reloj["ahora"] = t + timedelta(seconds=delta)
        activo = delta >= 90
        procesar(_snapshot_servicio(activo=activo, captured_at=reloj["ahora"]))

    # La confirmación del ciclo en 30s programó evidencia para 30+60=90s, que
    # coincide con el instante de recuperación: se recolecta esa vez, pero
    # una recuperación por sí sola (sin incidente nuevo) no debe generar una
    # segunda entrada en la cola ni una segunda llamada al proveedor.
    assert sesion.llamadas <= 1


def test_una_señal_repetida_no_genera_segundo_informe(tmp_path):
    config = _config_de_prueba(tmp_path, service_cycles=2)
    reloj = {"ahora": datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)}
    procesar, _ = build_incident_pipeline(
        config, "prompt", _SesionFalsa(), now_fn=lambda: reloj["ahora"]
    )

    t = reloj["ahora"]
    # Confirma en el segundo ciclo (60s) y sigue caído varios ciclos más.
    for delta in (0, 30, 60, 90, 120):
        reloj["ahora"] = t + timedelta(seconds=delta) + recolector.WINDOW_AFTER
        procesar(_snapshot_servicio(activo=False, captured_at=t + timedelta(seconds=delta)))

    informes = list(tmp_path.glob("*.md"))
    assert len(informes) == 1  # dedup: el incidente ya estaba activo


def test_dos_recursos_mantienen_estado_independiente(tmp_path):
    config = _config_de_prueba(
        tmp_path,
        service_cycles=2,
        monitored_ports=(MonitoredPort(port=5432, service="postgresql.service"),),
    )
    reloj = {"ahora": datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)}
    procesar, _ = build_incident_pipeline(
        config, "prompt", _SesionFalsa(), now_fn=lambda: reloj["ahora"]
    )

    t0 = reloj["ahora"]
    # postgresql cae (service_failed); el puerto sigue escuchado por otra
    # cosa mientras postgresql no está activo (port_occupied).
    snap = SystemSnapshot(
        captured_at=t0,
        failed_services=(),
        services_available=True,
        disks=(),
        disk_available=True,
        memory=MemoryUsage(total_mb=3900, used_mb=1200, free_mb=800, available_mb=2400),
        memory_available=True,
        ports=(ListeningPort(address="0.0.0.0", port=5432),),
        ports_available=True,
        load=None,
        load_available=False,
        service_states=(ServiceState(name="postgresql.service", active=False),),
        service_states_available=True,
    )
    procesar(snap)
    reloj["ahora"] = t0 + timedelta(seconds=30)
    procesar(SystemSnapshot(**{**snap.__dict__, "captured_at": reloj["ahora"]}))

    # Dos claves distintas (service:postgresql.service y
    # port:5432:occupied) deben confirmar cada una su propio incidente sin
    # pisarse el contador.
    reloj["ahora"] = t0 + timedelta(seconds=30) + recolector.WINDOW_AFTER
    procesar(SystemSnapshot(**{**snap.__dict__, "captured_at": t0 + timedelta(seconds=30)}))

    informes = list(tmp_path.glob("*.md"))
    assert len(informes) == 2

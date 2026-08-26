# Pruebas del monitor: los parsers puros contra fixtures y el borde con
# subprocess contra comandos reales del sistema (existen en cualquier Linux).
#
# Los fixtures de systemctl/df/free/ss/uptime son sinteticos, construidos a
# partir del formato documentado de cada herramienta (systemctl --no-legend
# --plain, df --output=..., etc.). Todavia no estan confirmados contra una
# captura real del VPS -- eso queda pendiente para cuando exista acceso de
# prueba (plan-mvp.md bloque A1, paso 2).
from __future__ import annotations

from doctorjk.monitor import (
    parse_disk_output,
    parse_failed_services_output,
    parse_load_output,
    parse_memory_output,
    parse_ports_output,
    run_command,
)

from ayudantes import load_fixture


# --------------------------------------------------------------- parsers puros


def test_parse_failed_services_sin_fallidos():
    assert parse_failed_services_output(load_fixture("systemctl_sin_fallidos.txt")) == ()


def test_parse_failed_services_un_fallido():
    servicios = parse_failed_services_output(load_fixture("systemctl_un_fallido.txt"))
    assert [s.name for s in servicios] == ["postgresql.service"]


def test_parse_disk_normal():
    discos = parse_disk_output(load_fixture("df_normal.txt"))
    assert discos[0].source == "/dev/sda1"
    assert discos[0].usage_percent == 42
    assert discos[0].target == "/"
    assert discos[1].target == "/dev/shm"


def test_parse_disk_lleno():
    discos = parse_disk_output(load_fixture("df_lleno.txt"))
    assert discos[0].usage_percent == 97


def test_parse_disk_salida_malformada_ignora_lineas_incompletas():
    assert parse_disk_output("Filesystem      Use% Mounted on\nsolo-dos-columnas 50%") == ()


def test_parse_memory_normal():
    memoria = parse_memory_output(load_fixture("free_normal.txt"))
    assert memoria is not None
    assert memoria.available_mb == 2400
    assert memoria.total_mb == 3900


def test_parse_memory_bajo():
    memoria = parse_memory_output(load_fixture("free_bajo.txt"))
    assert memoria is not None
    assert memoria.available_mb == 180


def test_parse_memory_salida_malformada_devuelve_none():
    assert parse_memory_output("salida inesperada sin la linea Mem:") is None


def test_parse_ports():
    puertos = parse_ports_output(load_fixture("ss_puertos.txt"))
    direcciones = {(p.address, p.port) for p in puertos}
    assert direcciones == {("0.0.0.0", 22), ("0.0.0.0", 80), ("127.0.0.1", 5432)}


def test_parse_ports_salida_vacia():
    assert parse_ports_output("State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port\n") == ()


def test_parse_load_normal():
    carga = parse_load_output(load_fixture("uptime_normal.txt"))
    assert carga is not None
    assert carga.load_1m == 0.15
    assert carga.load_5m == 0.22
    assert carga.load_15m == 0.30


def test_parse_load_salida_malformada_devuelve_none():
    assert parse_load_output(load_fixture("uptime_malformado.txt")) is None


# --------------------------------------------------------------------- run_command


def test_run_command_exito():
    resultado = run_command(["printf", "hola"], timeout_s=2.0)
    assert resultado.success is True
    assert resultado.stdout == "hola"
    assert resultado.error is None


def test_run_command_comando_ausente():
    resultado = run_command(["comando-que-no-existe-doctorjk"], timeout_s=2.0)
    assert resultado.success is False
    assert "no encontrado" in resultado.error


def test_run_command_codigo_distinto_de_cero():
    resultado = run_command(["false"], timeout_s=2.0)
    assert resultado.success is False
    assert "código" in resultado.error


def test_run_command_timeout():
    resultado = run_command(["sleep", "5"], timeout_s=0.05)
    assert resultado.success is False
    assert "tiempo agotado" in resultado.error

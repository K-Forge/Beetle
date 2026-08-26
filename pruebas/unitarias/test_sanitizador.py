# Pruebas del sanitizador (tareas #184, #185, plan-mvp.md Gate C3).
#
# Cubren los patrones de la tarea #184 (IPs, credenciales por variable,
# Bearer/JWT, claves SSH, rutas de home), casos adversariales de formato
# inesperado, y "no sobre-redacción": texto legítimo que NO debe tocarse.
from __future__ import annotations

from doctorjk.sanitizador import sanitize

# --------------------------------------------------------------------- IPs


def test_ipv4_simple_se_redacta():
    assert sanitize("conexion desde 192.168.1.10 rechazada") == "conexion desde [IP_1] rechazada"


def test_ipv4_con_puerto_se_redacta_solo_la_ip():
    assert sanitize("upstream 10.0.0.5:8080 timeout") == "upstream [IP_1]:8080 timeout"


def test_ipv4_dentro_de_url_se_redacta():
    resultado = sanitize("GET http://203.0.113.7/health 500")
    assert "203.0.113.7" not in resultado
    assert "[IP_1]" in resultado


def test_misma_ip_produce_el_mismo_placeholder_en_todo_el_texto():
    texto = "192.168.1.10 fallo\notra linea\n192.168.1.10 fallo de nuevo"
    resultado = sanitize(texto)
    apariciones = resultado.count("[IP_1]")
    assert apariciones == 2
    assert "192.168.1.10" not in resultado


def test_ips_distintas_reciben_placeholders_distintos_en_orden_de_aparicion():
    resultado = sanitize("10.0.0.1 hablo con 10.0.0.2")
    assert "[IP_1]" in resultado and "[IP_2]" in resultado
    assert resultado.index("[IP_1]") < resultado.index("[IP_2]")


def test_ipv4_en_formato_nginx_access_log():
    linea = '203.0.113.9 - - [25/Aug/2026:12:00:00] "GET / HTTP/1.1" 200 512'
    resultado = sanitize(linea)
    assert "203.0.113.9" not in resultado
    assert resultado.startswith("[IP_1] - -")


def test_ipv6_se_redacta():
    resultado = sanitize("origen 2001:db8:85a3::8a2e:370:7334 bloqueado")
    assert "2001:db8" not in resultado
    assert "[IP_1]" in resultado


# --------------------------------------------------------- credenciales por variable


def test_password_simple_se_redacta():
    assert sanitize("PASSWORD=hunter2") == "PASSWORD=[REDACTADO]"


def test_export_secret_key_se_redacta():
    assert sanitize("export SECRET_KEY=abc123xyz") == "export SECRET_KEY=[REDACTADO]"


def test_variable_con_password_como_sufijo_se_redacta():
    assert sanitize("DB_PASSWORD=s3cr3t") == "DB_PASSWORD=[REDACTADO]"


def test_token_con_valor_entre_comillas_se_redacta():
    resultado = sanitize('API_TOKEN="abc 123 con espacios"')
    assert resultado == 'API_TOKEN=[REDACTADO]'


def test_credencial_embebida_a_mitad_de_linea_se_redacta():
    resultado = sanitize("usuario=bob PASSWORD=hunter2 rol=admin")
    assert "hunter2" not in resultado
    assert "PASSWORD=[REDACTADO]" in resultado
    assert "usuario=bob" in resultado  # el resto de la línea no se toca


def test_variable_con_key_como_substring_no_relacionada_no_se_redacta():
    # "MONKEY" contiene "KEY" como subcadena pero no es una variable de
    # credenciales: no debe sobre-redactarse.
    assert sanitize("MONKEY_ISLAND=1") == "MONKEY_ISLAND=1"


def test_variable_sin_keyword_de_credencial_no_se_redacta():
    assert sanitize("PORT=8080") == "PORT=8080"


# --------------------------------------------------------------------- Bearer/JWT


def test_bearer_token_se_redacta():
    resultado = sanitize("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123signature")
    assert "eyJ" not in resultado
    assert "Authorization: Bearer [TOKEN_REDACTADO]" in resultado


def test_jwt_suelto_sin_bearer_se_redacta():
    resultado = sanitize(
        "cookie=session; jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ"
    )
    assert "[TOKEN_REDACTADO]" in resultado
    assert "eyJ" not in resultado


# ------------------------------------------------------------------ claves SSH


def test_clave_ssh_privada_openssh_se_redacta_completa():
    bloque = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAA\n"
        "MwAAAAtzc2gtZWQyNTUxOQAAACBsecretkeydata1234567890abcdef\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    resultado = sanitize(f"config encontrada:\n{bloque}\nfin del archivo")
    assert "b3BlbnNzaC1rZXktdjEA" not in resultado
    assert resultado == "config encontrada:\n[REDACTADO]\nfin del archivo"


def test_clave_ssh_publica_se_redacta_el_blob():
    resultado = sanitize("authorized_keys: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGZ1YWJjZGVm user@host")
    assert "AAAAC3NzaC1lZDI1NTE5" not in resultado
    assert resultado.startswith("authorized_keys: ssh-ed25519 [REDACTADO]")


# --------------------------------------------------------------------- rutas home


def test_ruta_home_enmascara_el_usuario():
    resultado = sanitize("leyendo /home/mauitu/.ssh/config")
    assert "mauitu" not in resultado
    assert resultado == "leyendo /home/[USUARIO]/.ssh/config"


def test_rutas_home_de_distintos_usuarios_se_enmascaran_ambas():
    resultado = sanitize("/home/alice/app.log y /home/bob/app.log")
    assert "alice" not in resultado
    assert "bob" not in resultado
    assert resultado.count("/home/[USUARIO]") == 2


# --------------------------------------------------------------- no sobre-redacción


def test_texto_sin_datos_sensibles_no_se_modifica():
    texto = "servicio postgresql.service falló con código 1"
    assert sanitize(texto) == texto


def test_version_de_paquete_con_forma_de_ip_no_deberia_confundir_al_modelo_sin_contexto():
    # Limitación conocida y documentada: 1.2.3.4 como versión de paquete es
    # indistinguible de una IP para un regex. Se prueba el comportamiento
    # actual (se redacta) para que quede visible, no para afirmar que es
    # ideal -- ver docs/sanitizador_limitaciones.md.
    resultado = sanitize("paquete actualizado a la version 1.2.3.4")
    assert "[IP_1]" in resultado


def test_numero_de_puerto_solo_no_se_redacta_como_ip():
    assert sanitize("puerto 8080 abierto") == "puerto 8080 abierto"


# ------------------------------------------------- credenciales dentro de URIs
# Fuga encontrada al ejecutar el Gate C contra evidencia real de beetle-vps: la
# IP del host se enmascaraba y la contraseña seguía en claro.


def test_contrasena_en_uri_de_postgres_se_redacta():
    resultado = sanitize("connecting to postgresql://app:cambia_esto@10.0.0.85:5432/cargatest")
    assert "cambia_esto" not in resultado
    # El esquema y el usuario sí se conservan: son diagnósticos.
    assert "postgresql://app:[REDACTADO]@" in resultado


def test_contrasena_en_uri_se_redacta_para_cualquier_esquema():
    for esquema in ("redis", "amqp", "mongodb", "https"):
        resultado = sanitize(f"fallo en {esquema}://usuario:hunter2@servidor/recurso")
        assert "hunter2" not in resultado, esquema


def test_uri_sin_credenciales_no_se_toca():
    # Sin "@" no hay credencial: el puerto no debe confundirse con una contraseña.
    texto = "upstream http://localhost:8080/salud respondió 502"
    assert "[REDACTADO]" not in sanitize(texto)


def test_uri_con_usuario_pero_sin_contrasena_no_se_rompe():
    texto = "conectando a ftp://anonimo@archivos.local/pub"
    assert sanitize(texto) == texto


# --------------------------------------------------------------- Basic auth


def test_cabecera_basic_se_redacta():
    # Basic transporta usuario:contraseña en base64; era tan sensible como
    # Bearer y pasaba sin tocar.
    resultado = sanitize("Authorization: Basic YWRtaW46c3VwZXJzZWNyZXRv")
    assert "YWRtaW46c3VwZXJzZWNyZXRv" not in resultado
    assert "Basic [REDACTADO]" in resultado


def test_palabra_basic_suelta_no_se_redacta():
    # No sobre-redacción: "basic" en prosa no es una cabecera de autorización.
    texto = "se aplicó la configuración basic del servicio"
    assert sanitize(texto) == texto

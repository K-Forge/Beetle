# Limitaciones conocidas del sanitizador

`doctorjk/sanitizador.py` (tarea #184) enmascara datos sensibles por
expresiones regulares. Es una defensa por patrones, no un parser semántico:
"un dato sensible con formato inesperado puede escaparse" (documento de
proyecto, sección 5.3). Este documento deja constancia explícita de qué NO
cubre, tal como pide la tarea #185, para que nadie asuma una garantía que el
sanitizador no ofrece.

## 1. Direcciones IPv6 con compresión `::`

El patrón de IPv6 no entiende la sintaxis de compresión `::` (que reemplaza
una corrida de grupos en cero). Una dirección como
`2001:db8:85a3::8a2e:370:7334` no se redacta como una sola unidad: el regex
la parte en dos coincidencias independientes (`2001:db8:85a3` y
`8a2e:370:7334`), cada una con su propio placeholder `[IP_N]`. El resultado
sigue sin exponer la dirección real, pero rompe la consistencia que pide la
tarea #184 ("la misma IP siempre el mismo placeholder"): dos apariciones de
la misma dirección completa no producen el mismo par de placeholders si
aparecen en contextos distintos donde el orden de aparición de cada mitad
cambia. Además, la forma más comprimida (`::1`, `fe80::`) no matchea en
absoluto porque el patrón exige un dígito hexadecimal antes de cada `:`.

**Riesgo residual:** bajo. La dirección no se filtra sin enmascarar; el
problema es de consistencia y de cobertura en el extremo comprimido, no de
fuga de datos.

## 2. Direcciones MAC redactadas como si fueran IPv6

Una MAC (`00:1A:2B:3C:4D:5E`) tiene la misma forma que una IPv6 de 6 grupos
hexadecimales de hasta 4 caracteres y el regex no distingue una de otra: se
redacta igual que una IP. No es una fuga (una MAC también es un
identificador de red que vale la pena enmascarar), pero el informe final
etiqueta una MAC como `[IP_N]`, lo cual puede confundir al modelo si la
distinción importaba para el diagnóstico.

**Riesgo residual:** bajo, cosmético.

## 3. Filtro de fecha/hora puede dejar pasar una IPv6 real all-decimal

Para evitar el falso positivo más común -- un timestamp como
`25/Aug/2026:12:00:00` (formato estándar de access log de nginx) calzando
con el patrón de IPv6 -- se descarta cualquier candidato de 4 grupos o
menos donde todos los grupos son dígitos decimales puros. Esto es correcto
para timestamps, pero también dejaría sin redactar una IPv6 real que por
coincidencia esté escrita enteramente en dígitos decimales y con pocos
grupos (p. ej. `2001:0:0:1`). Es un caso legítimo pero estadísticamente muy
raro: las IPv6 reales casi siempre incluyen al menos una letra hexadecimal.

**Riesgo residual:** bajo, y es la contrapartida deliberada de la tarea #1
(no vale la pena resolver un caso raro a costa de romper el caso común de
todos los logs con marca de tiempo).

## 4. Credenciales en formato `clave: valor` o JSON no se detectan

`_redact_credential_assignments` solo reconoce asignaciones de shell/`.env`
con `=` (`PASSWORD=...`, `export SECRET_KEY=...`). Un valor sensible escrito
como YAML (`password: hunter2`) o como JSON (`{"password": "hunter2"}`) no
coincide con el patrón y viaja sin enmascarar. Tampoco se cubre un valor que
ocupa más de una línea (un certificado o token pegado con saltos de línea
dentro de una asignación).

**Riesgo residual:** medio. Configuraciones modernas (contenedores,
`docker-compose.yml`, respuestas de API) usan estos formatos con frecuencia.

## 5. Nombres de variable de credenciales en español, o sin keyword reconocible

Las palabras clave que activan el enmascarado de una asignación son
`PASSWORD`, `SECRET`, `KEY`, `TOKEN` (inglés, sección 5.3 del documento de
proyecto). Una variable como `CONTRASENA=...` o `CLAVE_API=...` no las
contiene y no se redacta. Tampoco se redacta un valor sensible asignado a un
nombre genérico sin ninguna de esas palabras (`DB_CONN=usuario:hunter2@host`,
donde la credencial va embebida dentro del valor de una variable con nombre
inocuo).

**Riesgo residual:** medio-alto si el software del cliente usa
convenciones de nombres distintas a las cubiertas.

## 6. Secretos opacos sin contexto reconocible

Un valor con forma de secreto (una cadena base64 larga, una API key) que
aparece suelto en una línea de log -- sin `Bearer`, sin la forma de tres
segmentos de un JWT, y sin una variable `KEY=`/`TOKEN=` que lo anteceda --
no tiene ningún patrón que lo distinga de cualquier otra cadena alfanumérica
y pasa sin redactar.

**Riesgo residual:** medio. Depende de cuánto "loguee" la aplicación del
cliente sus propias credenciales sin una convención reconocible.

---

Ninguna de estas limitaciones es una fuga masiva ni sistemática: los cinco
patrones de la tarea #184 (IPs, variables de credenciales con keyword
reconocible, Bearer/JWT, claves SSH, rutas de home) cubren el caso más común
de cada categoría con el 100 % de los tests de `test_sanitizador.py`
pasando. Este documento existe para que nadie -- ni el equipo, ni el cliente
-- asuma que el sanitizador es una garantía absoluta de privacidad.

# pdf-extractext-extractor

> Microservicio sin estado que recibe un PDF y devuelve su texto en Markdown, la
> cantidad de páginas y sus metadatos. Es el extractor de
> [pdf-extractext](https://github.com/Extractor-de-texto-PDF-Grupo-06/pdf-extractext-orchestration)
> y el microservicio evaluado en el TP de Test de Carga, Estrés y Optimización.

**Universidad Tecnológica Nacional — Facultad Regional San Rafael**
**Ingeniería en Sistemas | Desarrollo de Software 2026**

**Integrantes: Mansalve Augusto, Praderio Valentín, Quiroga Constanza**

---

## Qué hace

```
POST /extract   body: los bytes del PDF (Content-Type: application/pdf)
→ 200 {"content": "# Título\n\nTexto...", "page_count": 12, "metadata": {"title": "..."}}
GET  /health
→ 200
```

Responde 422 si el archivo no es un PDF válido, está corrupto o pide contraseña; 413 si
supera `MAX_FILE_SIZE_MB` (10 por defecto), y 503 si está saturado. El contrato completo
está en [`docs/extractor_contract.md`](docs/extractor_contract.md). `metadata` trae solo lo
que el PDF declara sobre sí mismo (título, autor, fechas…) y puede ser `{}`.

No guarda nada: no tiene base de datos y el PDF nunca se escribe a disco. En el sistema,
web lo llama por el entrypoint interno de Traefik, que balancea las réplicas; el
despliegue completo está en
[`pdf-extractext-orchestration`](https://github.com/Extractor-de-texto-PDF-Grupo-06/pdf-extractext-orchestration).

## Arquitectura

En el sistema, Traefik reparte entre las réplicas. El `docker-compose.yml` de este
repositorio es solo el entorno del TP de carga, con nginx como balanceador:

```
cliente ──► extractor-lb (nginx, least_conn) ──► extractor × 5 réplicas (1 CPU, 1 GB c/u)
```

- **extractor:** FastAPI + uvicorn. La extracción (PyMuPDF con un conversor a Markdown
  propio) corre en un pool de procesos, fuera del event loop. La recepción del PDF
  y la extracción tienen controles separados: hasta 32 PDFs en recepción/cola y
  una extracción activa por réplica. Cada adquisición tiene una espera máxima
  de `QUEUE_TIMEOUT_S`; un presupuesto total de `REQUEST_TIMEOUT_S` (25 s)
  cubre recepción, colas y procesamiento. Si se supera, responde 503. Los PDFs
  pasan al proceso por memoria compartida reutilizable; una cancelación conserva
  el buffer y cupo de CPU hasta que termina el trabajo real.
- **extractor-lb:** nginx con conexiones HTTP persistentes, reparto `least_conn`
  compartido y envío directo del body para PDFs de varios MB.

El porqué de cada decisión, con mediciones, está en el
[informe de carga](docs/informe-carga.md).

El [informe de refactorización](docs/refactor-2026-10-08.md) resume arquitectura, investigación, antes/después y condiciones de carga. Incluye dos JSON originales y un enlace al respaldo completo.

| Tecnología | Uso |
|---|---|
| **Python 3.12 + FastAPI** | API HTTP |
| **PyMuPDF** | Extracción del texto y su formato |
| **uv** | Dependencias (`pyproject.toml` + `uv.lock`) |
| **pytest** | Tests (TDD) |
| **Docker Compose + nginx** | Réplicas y balanceo |
| **k6 y Vegeta** | Pruebas de carga y estrés |

## Configuración

Por variables de entorno (ver [`.env.example`](.env.example)):

| Variable | Por defecto | Para qué |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `10` | Tamaño máximo del PDF; más grande responde 413 |
| `WORKERS` | `1` | Procesos que extraen en paralelo; uno por CPU |
| `MAX_INFLIGHT` | `32` | PDFs en recepción o en cola por réplica |
| `QUEUE_TIMEOUT_S` | `20` | Espera máxima por un lugar antes de responder 503 |
| `REQUEST_TIMEOUT_S` | `25` | Presupuesto total del pedido; menor que el timeout del cliente (30 s) |
| `PORT` | `8000` | Puerto HTTP de la imagen |

## Desarrollo

```bash
uv sync
uv run pytest
docker build -t pdf-extractext-extractor:dev .
```

La imagen es multi-stage, corre con el usuario `10001`, declara un `HEALTHCHECK` contra
`/health` y funciona con el sistema de archivos en solo lectura. La CI corre los tests,
`pip-audit` y Trivy, y al fusionar en `main` publica la imagen en
`ghcr.io/extractor-de-texto-pdf-grupo-06/pdf-extractext-extractor`.

## Ejecución para el TP de carga

```bash
docker compose up --build -d
```

El servicio queda en `http://localhost:8080/extract` (el puerto se cambia con
`EXTRACTOR_PORT`; ver [`.env.example`](.env.example)). Para probarlo a mano:

```bash
curl -X POST --data-binary @archivo.pdf -H "Content-Type: application/pdf" http://localhost:8080/extract
```

## Pruebas de carga y estrés

> [!IMPORTANT]
> Los 4 PDFs oficiales de la cátedra no están en el repo (son material de terceros).
> Antes de correr las pruebas hay que copiarlos en `tests/stress/pdfs/` con sus nombres
> originales; la lista está en [`tests/stress/README.md`](tests/stress/README.md#pdfs-de-prueba).

Con el servicio levantado:

```bash
docker compose run --rm --service-ports k6
docker compose run --rm vegeta
```

Los resultados quedan en `tests/stress/results/`. Para usar los scripts de la cátedra en vez de
los nuestros, alcanza con apuntarlos a `http://localhost:8080/extract`.

- Cómo correrlas, perfiles y opciones: [`tests/stress/README.md`](tests/stress/README.md)
- Arquitectura, mediciones y proceso de optimización: [`docs/informe-carga.md`](docs/informe-carga.md)
- Corrida final con sus reportes: [`docs/evidencia/`](docs/evidencia/README.md)
- Checklist punto por punto contra la consigna: [`docs/checklist-consigna.md`](docs/checklist-consigna.md)

## Principios aplicados

- **12-Factor:** configuración por variables de entorno, dependencias explícitas con
  `uv.lock`, proceso sin estado que escala por réplicas, logs a stdout.
- **TDD, KISS, YAGNI, DRY y SOLID.**

## Seguridad de la imagen

El escaneo Trivy 0.76.2 del 22/11/2026 sobre Debian 13.8 encontró 12 CVE de severidad alta
sin versión corregida disponible en Debian y ninguna crítica: CVE-2025-69720,
CVE-2026-119373, CVE-2026-119374, CVE-2026-119379, CVE-2026-124709, CVE-2026-16742,
CVE-2026-54369, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 y
CVE-2026-9538. Afectan paquetes del sistema base (ncurses, SQLite, OpenSSL, systemd,
acl, util-linux y Perl), no dependencias Python de la aplicación. La imagen ejecuta como
UID 10001 y, en orchestration, Compose aplica `read_only`, `cap_drop: [ALL]` y
`no-new-privileges:true`. La CI ignora solo hallazgos sin corrección publicada; cuando
Trivy detecte una versión corregida, el hallazgo vuelve a bloquearla.

## Licencia

MIT © 2026 — Universidad Tecnológica Nacional

# API REST IoT (AWS Chalice)

API Gateway + Lambda creadas por **Chalice**. No forma parte del Terraform de `../infraestructura`: Chalice crea y borra sus propios recursos (`chalice deploy` / `chalice delete`). En el Learner Lab usa el rol existente `LabRole` (`autogen_policy: false`, `manage_iam_role: false`).

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/eventos` | Valida el JSON e **invoca `iot_publisher_lambda`** (síncrono). Devuelve la key del objeto S3 y la lectura publicada. No escribe en S3 ni en DynamoDB. |
| `GET` | `/sensores/{sensor_id}` | `query` sobre `iot_lecturas` por `device_id`, **más recientes primero**. `?limit=N` (1–1000) es opcional; sin él devuelve todas. |

### POST /eventos

Body JSON con:
- **id del sensor**: `device_id` o `sensor_id` (texto de 1 a 64 caracteres: letras, números, `_ . : -`).
- **al menos una medición**: cualquier campo (`temperature`, `humidity`, `tipo`/`valor`, `ruido`...).
- `timestamp` opcional (texto ISO 8601).

```json
{"device_id": "sensor-01", "temperature": 23.5, "humidity": 60}
{"sensor_id": "ruido-01", "tipo": "ruido", "valor": 72.4}
```

Respuesta `200`:

```json
{"mensaje": "evento publicado", "key": "events/sensor-01/<uuid>.json",
 "lectura": {"device_id": "sensor-01", "timestamp": "2026-11-25T15:00:00+00:00", "temperature": 23.5, "humidity": 60}}
```

### GET /sensores/{sensor_id}

```json
{"sensor_id": "sensor-01", "cantidad": 1,
 "lecturas": [{"device_id": "sensor-01", "timestamp": "...", "temperature": 23.5, "humidity": 60, "s3_key": "events/..."}]}
```

Un sensor sin lecturas devuelve `200` con `"cantidad": 0`.

### Errores

| Código | Cuándo |
|---|---|
| `400` | Body que no es JSON u objeto, sin id de sensor, id inválido, sin mediciones, `device_id` ≠ `sensor_id`, `timestamp` no texto, `limit` inválido. Cuerpo: `{"Code": "BadRequestError", "Message": "..."}` |
| `415` | `Content-Type` distinto de `application/json` en el POST. |
| `502` | La publisher no existe o falló, o DynamoDB no respondió. Cuerpo: `{"error": "..."}` |

## Configuración

`.chalice/config.json` (stage `dev`):

| Variable | Valor |
|---|---|
| `TABLE_NAME` | `iot_lecturas` |
| `PUBLISHER_FUNCTION` | `iot_publisher_lambda` |
| `iam_role_arn` | `arn:aws:iam::<cuenta>:role/LabRole`. `deploy.sh` lo rellena con tu cuenta. |

## Uso

Paso a paso completo (Windows, Learner Lab): ver [../GUIA-PASO-A-PASO.md](../GUIA-PASO-A-PASO.md).

Dentro del contenedor `iot_dev_environment`, desde `/app`:

```bash
make api-test     # pruebas locales (sin AWS)
make api-deploy   # chalice deploy (requiere la infra y las lambdas desplegadas)
make api-smoke    # POST + GET contra la API desplegada
make api-delete   # chalice delete
```

Ejemplos con `curl`:

```bash
URL=$(make -s api-url)
curl -X POST ${URL}eventos -H 'Content-Type: application/json'   -d '{"device_id":"sensor-01","temperature":23.5,"humidity":60}'
curl ${URL}sensores/sensor-01
curl "${URL}sensores/sensor-01?limit=5"
```

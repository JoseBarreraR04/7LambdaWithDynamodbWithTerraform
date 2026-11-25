"""API REST del pipeline IoT (AWS Chalice).

POST /eventos              -> invoca la lambda iot_publisher_lambda con el JSON del sensor
GET  /sensores/{sensor_id} -> consulta las lecturas del sensor en DynamoDB (iot_lecturas)

La API no escribe en S3 ni en DynamoDB: el POST solo dispara la publisher;
el resto del flujo (S3 -> ingestor -> DynamoDB) ya existe.
"""
import json
import os
import re
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError
from chalice import BadRequestError, Chalice, Response

app = Chalice(app_name="iot-api")

# Ids permitidos: letras, números y _ . : - (máx. 64). Evita rutas raras en S3.
ID_VALIDO = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MAX_LIMIT = 1000

_clientes = {}


def lambda_client():
    if "lambda" not in _clientes:
        _clientes["lambda"] = boto3.client("lambda")
    return _clientes["lambda"]


def tabla():
    if "tabla" not in _clientes:
        _clientes["tabla"] = boto3.resource("dynamodb").Table(os.environ.get("TABLE_NAME", "iot_lecturas"))
    return _clientes["tabla"]


def _rechazar_constante(valor):
    # json.loads acepta NaN/Infinity por defecto; DynamoDB no.
    raise ValueError(f"valor no permitido: {valor}")


def a_numero(obj):
    """Convierte recursivamente los Decimal de DynamoDB a int/float."""
    if isinstance(obj, list):
        return [a_numero(v) for v in obj]
    if isinstance(obj, dict):
        return {k: a_numero(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def error(status, mensaje):
    return Response(status_code=status, body={"error": mensaje})


@app.route("/eventos", methods=["POST"], content_types=["application/json"])
def crear_evento():
    try:
        body = json.loads(app.current_request.raw_body or b"", parse_constant=_rechazar_constante)
    except (ValueError, TypeError):
        raise BadRequestError("El body debe ser un JSON válido")
    if not isinstance(body, dict):
        raise BadRequestError("El body debe ser un objeto JSON")

    device_id = body.get("device_id")
    sensor_id = body.get("sensor_id")
    if device_id is not None and sensor_id is not None and device_id != sensor_id:
        raise BadRequestError("device_id y sensor_id no coinciden")
    id_sensor = device_id if device_id is not None else sensor_id
    if not isinstance(id_sensor, str) or not ID_VALIDO.match(id_sensor):
        raise BadRequestError(
            "Falta el id del sensor ('device_id' o 'sensor_id'): texto de 1 a 64 caracteres "
            "(letras, números, _ . : -)")

    if "timestamp" in body and not isinstance(body["timestamp"], str):
        raise BadRequestError("'timestamp' debe ser un texto (ISO 8601)")

    mediciones = {k: v for k, v in body.items() if k not in ("device_id", "sensor_id", "timestamp")}
    if not mediciones:
        raise BadRequestError("El evento no trae mediciones (p. ej. temperature, humidity, tipo/valor)")

    payload = dict(mediciones, device_id=id_sensor)
    if "timestamp" in body:
        payload["timestamp"] = body["timestamp"]

    funcion = os.environ.get("PUBLISHER_FUNCTION", "iot_publisher_lambda")
    try:
        resp = lambda_client().invoke(
            FunctionName=funcion,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        resultado = json.loads(resp["Payload"].read() or b"null")
    except (ClientError, BotoCoreError) as exc:
        app.log.error("Error invocando %s: %s", funcion, exc)
        return error(502, f"No se pudo invocar la lambda {funcion}: {exc}")

    if resp.get("FunctionError") or not isinstance(resultado, dict) or resultado.get("statusCode") != 200:
        app.log.error("La lambda %s falló: %s", funcion, resultado)
        return error(502, f"La lambda {funcion} devolvió un error")

    detalle = resultado.get("body")
    if isinstance(detalle, str):
        detalle = json.loads(detalle)
    return {"mensaje": "evento publicado", **(detalle or {})}


@app.route("/sensores/{sensor_id}", methods=["GET"])
def lecturas_sensor(sensor_id):
    if not ID_VALIDO.match(sensor_id or ""):
        raise BadRequestError("Id de sensor inválido")

    params = app.current_request.query_params or {}
    limit = None
    if "limit" in params:
        try:
            limit = int(params["limit"])
        except ValueError:
            limit = 0
        if not 1 <= limit <= MAX_LIMIT:
            raise BadRequestError(f"'limit' debe ser un entero entre 1 y {MAX_LIMIT}")

    # Más recientes primero (orden descendente por timestamp)
    consulta = {"KeyConditionExpression": Key("device_id").eq(sensor_id), "ScanIndexForward": False}
    items = []
    try:
        while True:
            if limit:
                consulta["Limit"] = limit - len(items)
            resp = tabla().query(**consulta)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp or (limit and len(items) >= limit):
                break
            consulta["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    except (ClientError, BotoCoreError) as exc:
        app.log.error("Error consultando DynamoDB: %s", exc)
        return error(502, f"No se pudo consultar DynamoDB: {exc}")

    return {"sensor_id": sensor_id, "cantidad": len(items), "lecturas": a_numero(items)}

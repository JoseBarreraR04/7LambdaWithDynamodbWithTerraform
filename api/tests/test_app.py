"""Pruebas locales de la API (sin AWS): Chalice test client + moto."""
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from chalice.test import Client
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as api  # noqa: E402

JSON = {"Content-Type": "application/json"}


class LambdaFalsa:
    """Reemplaza al cliente de Lambda: guarda el payload y responde como la publisher."""

    def __init__(self, function_error=False):
        self.llamadas = []
        self.function_error = function_error

    def invoke(self, FunctionName, InvocationType, Payload):
        evento = json.loads(Payload)
        self.llamadas.append((FunctionName, InvocationType, evento))
        if self.function_error:
            return {"FunctionError": "Unhandled",
                    "Payload": io.BytesIO(b'{"errorMessage": "boom"}')}
        cuerpo = {"key": f"events/{evento['device_id']}/x.json", "lectura": evento}
        return {"Payload": io.BytesIO(json.dumps({"statusCode": 200, "body": json.dumps(cuerpo)}).encode())}


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("TABLE_NAME", "tabla-test")
    monkeypatch.setenv("PUBLISHER_FUNCTION", "iot_publisher_lambda")
    api._clientes.clear()
    yield
    api._clientes.clear()


@pytest.fixture
def lambda_falsa():
    falsa = LambdaFalsa()
    api._clientes["lambda"] = falsa
    return falsa


def post(client, body):
    datos = body if isinstance(body, str) else json.dumps(body)
    return client.http.post("/eventos", headers=JSON, body=datos)


# ---------------- POST /eventos ----------------

def test_post_invoca_publisher(lambda_falsa):
    with Client(api.app) as client:
        r = post(client, {"device_id": "sensor-01", "temperature": 23.5, "humidity": 60})
    assert r.status_code == 200
    assert r.json_body["mensaje"] == "evento publicado"
    assert r.json_body["key"].startswith("events/sensor-01/")
    nombre, tipo, evento = lambda_falsa.llamadas[0]
    assert (nombre, tipo) == ("iot_publisher_lambda", "RequestResponse")
    assert evento == {"device_id": "sensor-01", "temperature": 23.5, "humidity": 60}


def test_post_sensor_generico_con_sensor_id(lambda_falsa):
    with Client(api.app) as client:
        r = post(client, {"sensor_id": "ruido-01", "tipo": "ruido", "valor": 72.4})
    assert r.status_code == 200
    assert lambda_falsa.llamadas[0][2] == {"device_id": "ruido-01", "tipo": "ruido", "valor": 72.4}


@pytest.mark.parametrize("body", [
    "esto no es json",
    "",
    "[1, 2]",
    '{"device_id": "s1", "temperature": NaN}',
    {"temperature": 20},                                    # sin id
    {"device_id": "", "temperature": 20},                   # id vacío
    {"device_id": 123, "temperature": 20},                  # id no texto
    {"device_id": "a/b", "temperature": 20},                # caracteres no permitidos
    {"device_id": "s1"},                                    # sin mediciones
    {"device_id": "s1", "sensor_id": "s2", "valor": 1},     # ids distintos
    {"device_id": "s1", "timestamp": 5, "valor": 1},        # timestamp no texto
])
def test_post_invalido_400(lambda_falsa, body):
    with Client(api.app) as client:
        r = post(client, body)
    assert r.status_code == 400
    assert lambda_falsa.llamadas == []


def test_post_error_de_lambda_502():
    api._clientes["lambda"] = LambdaFalsa(function_error=True)
    with Client(api.app) as client:
        r = post(client, {"device_id": "s1", "valor": 1})
    assert r.status_code == 502


# ---------------- GET /sensores/{id} ----------------

@pytest.fixture
def tabla_con_datos():
    with mock_aws():
        t = boto3.resource("dynamodb").create_table(
            TableName="tabla-test",
            KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"},
                       {"AttributeName": "timestamp", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"},
                                  {"AttributeName": "timestamp", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for i in range(5):
            t.put_item(Item={
                "device_id": "sensor-01",
                "timestamp": f"2026-01-0{i + 1}T00:00:00+00:00",
                "temperature": Decimal(f"2{i}.5"),
                "humidity": Decimal(60),
            })
        t.put_item(Item={"device_id": "otro", "timestamp": "2026-01-01", "valor": Decimal(1)})
        yield t


def test_get_lecturas_mas_recientes_primero(tabla_con_datos):
    with Client(api.app) as client:
        r = client.http.get("/sensores/sensor-01")
    assert r.status_code == 200
    cuerpo = r.json_body
    assert cuerpo["sensor_id"] == "sensor-01" and cuerpo["cantidad"] == 5
    fechas = [l["timestamp"] for l in cuerpo["lecturas"]]
    assert fechas == sorted(fechas, reverse=True)
    # Decimal convertido a número: 24.5 float y 60 entero
    assert cuerpo["lecturas"][0]["temperature"] == 24.5
    assert cuerpo["lecturas"][0]["humidity"] == 60 and isinstance(cuerpo["lecturas"][0]["humidity"], int)


def test_get_con_limit(tabla_con_datos):
    with Client(api.app) as client:
        r = client.http.get("/sensores/sensor-01?limit=2")
    assert r.status_code == 200
    assert [l["timestamp"][:10] for l in r.json_body["lecturas"]] == ["2026-01-05", "2026-01-04"]


@pytest.mark.parametrize("limit", ["0", "-1", "abc", "1001"])
def test_get_limit_invalido_400(tabla_con_datos, limit):
    with Client(api.app) as client:
        r = client.http.get(f"/sensores/sensor-01?limit={limit}")
    assert r.status_code == 400


def test_get_sensor_sin_lecturas(tabla_con_datos):
    with Client(api.app) as client:
        r = client.http.get("/sensores/no-existe")
    assert r.status_code == 200
    assert r.json_body == {"sensor_id": "no-existe", "cantidad": 0, "lecturas": []}


def test_raiz_lista_endpoints():
    with Client(api.app) as client:
        r = client.http.get("/")
    assert r.status_code == 200
    assert r.json_body["estado"] == "ok" and "POST /eventos" in r.json_body["endpoints"]

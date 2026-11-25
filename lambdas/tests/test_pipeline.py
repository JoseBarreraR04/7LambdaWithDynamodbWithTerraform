"""Prueba local del flujo completo con moto (AWS simulado en memoria)."""
import importlib.util
import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

SRC = Path(__file__).resolve().parents[1] / "src"


def cargar(nombre):
    spec = importlib.util.spec_from_file_location(f"{nombre}_fn", SRC / nombre / "lambda_function.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("BUCKET_NAME", "bucket-test")
    monkeypatch.setenv("TABLE_NAME", "tabla-test")


def test_publicar_y_a_ingestar():
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="bucket-test")
        ddb = boto3.resource("dynamodb")
        tabla = ddb.create_table(
            TableName="tabla-test",
            KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"},
                       {"AttributeName": "timestamp", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"},
                                  {"AttributeName": "timestamp", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # 1) La publicadora escribe el JSON en S3
        publisher = cargar("publisher")
        resp = publisher.lambda_handler({"device_id": "sensor-42"}, None)
        key = json.loads(resp["body"])["key"]
        assert s3.get_object(Bucket="bucket-test", Key=key)

        # 2) Simulamos el evento que S3 enviaría a la ingestora
        evento_s3 = {"Records": [{"s3": {"bucket": {"name": "bucket-test"},
                                         "object": {"key": key}}}]}
        ingestor = cargar("ingestor")
        assert ingestor.lambda_handler(evento_s3, None)["insertados"] == 1

        # 3) Verificamos DynamoDB
        items = tabla.scan()["Items"]
        assert len(items) == 1 and items[0]["device_id"] == "sensor-42"


def test_sensor_generico_sin_temperatura():
    """Un sensor de ruido (sin temperature) recorre todo el flujo."""
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="bucket-test")
        tabla = boto3.resource("dynamodb").create_table(
            TableName="tabla-test",
            KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"},
                       {"AttributeName": "timestamp", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"},
                                  {"AttributeName": "timestamp", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        publisher = cargar("publisher")
        resp = publisher.lambda_handler({"sensor_id": "ruido-01", "tipo": "ruido", "valor": 72.4}, None)
        cuerpo = json.loads(resp["body"])
        # Se publica tal cual, sin datos simulados
        assert cuerpo["lectura"]["device_id"] == "ruido-01"
        assert "temperature" not in cuerpo["lectura"]

        evento_s3 = {"Records": [{"s3": {"bucket": {"name": "bucket-test"},
                                         "object": {"key": cuerpo["key"]}}}]}
        assert cargar("ingestor").lambda_handler(evento_s3, None)["insertados"] == 1

        item = tabla.scan()["Items"][0]
        assert item["device_id"] == "ruido-01"
        assert item["tipo"] == "ruido" and float(item["valor"]) == 72.4
        assert item["s3_key"] == cuerpo["key"]


def test_publisher_sin_mediciones_simula_lectura():
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="bucket-test")
        lectura = json.loads(cargar("publisher").lambda_handler({"device_id": "s1"}, None)["body"])["lectura"]
        assert {"temperature", "humidity", "timestamp"} <= lectura.keys()

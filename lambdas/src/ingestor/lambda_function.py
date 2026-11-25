"""Lambda ingestora: la dispara S3 al crearse un JSON; lo lee y lo
inserta en DynamoDB.

Acepta lecturas de cualquier tipo de sensor: solo exige las claves de la
tabla (device_id y timestamp) y guarda el resto de campos tal cual.
"""
import json
import os
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    table = dynamodb.Table(os.environ["TABLE_NAME"])
    insertados = 0

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # Las claves llegan codificadas en URL (espacios como '+', etc.)
        key = unquote_plus(record["s3"]["object"]["key"])

        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        # parse_float=Decimal: DynamoDB no acepta float
        lectura = json.loads(body, parse_float=Decimal)

        if not isinstance(lectura, dict) or not lectura.get("device_id") or not lectura.get("timestamp"):
            print(f"Ignorado s3://{bucket}/{key}: falta device_id o timestamp")
            continue

        item = dict(lectura)
        item["device_id"] = str(item["device_id"])
        item["timestamp"] = str(item["timestamp"])
        item["s3_key"] = key
        table.put_item(Item=item)
        insertados += 1
        print(f"Insertado {item['device_id']} @ {item['timestamp']} desde s3://{bucket}/{key}")

    return {"statusCode": 200, "insertados": insertados}


def main():
    """Prueba local: arma el evento que S3 enviaría y llama al handler
    desde el PC contra el bucket y la tabla reales en AWS.

    Uso:
        BUCKET_NAME=<bucket> python lambda_function.py <key>

    <key> es la clave de un JSON ya publicado (p. ej. la que imprime la
    lambda publisher). TABLE_NAME por defecto es "iot_lecturas".
    """
    import sys

    if len(sys.argv) < 2 or "BUCKET_NAME" not in os.environ:
        sys.exit("Uso: BUCKET_NAME=<bucket> python lambda_function.py <key>")

    os.environ.setdefault("TABLE_NAME", "iot_lecturas")
    evento_s3 = {"Records": [{"s3": {"bucket": {"name": os.environ["BUCKET_NAME"]},
                                     "object": {"key": sys.argv[1]}}}]}
    print(lambda_handler(evento_s3, None))


if __name__ == "__main__":
    main()

"""Lambda publicadora: recibe la lectura de un sensor (de cualquier tipo:
temperatura, humedad, ruido, luz...) y la publica como archivo JSON en S3.

Si la invocación no trae mediciones (solo el id del sensor), simula una
lectura de temperatura/humedad, como hacía el ejemplo original.
"""
import json
import os
import random
import uuid
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")


def armar_lectura(event):
    """Construye la lectura a partir del evento recibido.

    - El id puede venir como "device_id" o "sensor_id" (se guarda como device_id,
      que es la clave de partición de la tabla).
    - "timestamp" es opcional; si no viene se usa la hora actual (UTC).
    - Cualquier otro campo se considera una medición y se guarda tal cual.
    """
    datos = dict(event or {})
    device_id = datos.pop("device_id", None) or datos.pop("sensor_id", None) or "sensor-01"
    datos.pop("sensor_id", None)
    timestamp = datos.pop("timestamp", None) or datetime.now(timezone.utc).isoformat()

    lectura = {"device_id": str(device_id), "timestamp": str(timestamp)}
    if datos:
        # Vienen mediciones reales: se publican sin modificar
        lectura.update(datos)
    else:
        # Sin mediciones: lectura simulada (útil para "make invoke")
        lectura["temperature"] = round(random.uniform(18.0, 35.0), 2)
        lectura["humidity"] = round(random.uniform(30.0, 70.0), 2)
    return lectura


def lambda_handler(event, context):
    bucket = os.environ["BUCKET_NAME"]
    lectura = armar_lectura(event)

    key = f"events/{lectura['device_id']}/{uuid.uuid4()}.json"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(lectura),
        ContentType="application/json",
    )
    print(f"Publicado s3://{bucket}/{key}")
    return {"statusCode": 200, "body": json.dumps({"key": key, "lectura": lectura})}


def main():
    """Prueba local: llama al handler desde el PC contra el bucket real en AWS.

    Uso:
        BUCKET_NAME=<bucket> python lambda_function.py [device_id]

    El nombre del bucket se obtiene con:
        terraform -chdir=infraestructura output -raw bucket_name
    """
    import sys

    if "BUCKET_NAME" not in os.environ:
        sys.exit("Falta BUCKET_NAME")

    device_id = sys.argv[1] if len(sys.argv) > 1 else "sensor-01"
    resp = lambda_handler({"device_id": device_id}, None)
    print(json.dumps(json.loads(resp["body"]), indent=2))


if __name__ == "__main__":
    main()

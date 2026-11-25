# Pipeline IoT: API → Lambda → S3 → Lambda → DynamoDB

Una API REST (Chalice) recibe la lectura de un sensor e invoca una lambda que la publica como JSON en S3; el bucket dispara otra lambda que la inserta en DynamoDB. La API también permite consultar las lecturas de un sensor.

## Arquitectura

![Arquitectura](docs/arquitectura.png)

```mermaid
flowchart LR
    C[Cliente / Sensor] -->|POST /eventos| API[API Chalice<br/>API Gateway + Lambda]
    API -->|lambda.invoke| P[Lambda iot_publisher_lambda]
    P -->|PutObject JSON| S3[(Bucket S3)]
    S3 -->|ObjectCreated| I[Lambda iot_ingestor_lambda]
    I -->|PutItem| D[(DynamoDB iot_lecturas)]
    C2[Cliente] -->|GET /sensores/id| API
    API -->|Query device_id| D
```

## Flujo de un evento

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant A as API Chalice
    participant P as Lambda publisher
    participant S3 as Bucket S3
    participant I as Lambda ingestor
    participant D as DynamoDB

    C->>A: POST /eventos {device_id, ...}
    A->>P: lambda.invoke(payload)
    P->>S3: PutObject events/<device>/<uuid>.json
    P-->>A: key del objeto
    A-->>C: 200 evento publicado
    S3-)I: Notificación s3:ObjectCreated (async)
    I->>S3: GetObject (lee el JSON)
    I->>D: PutItem (device_id, timestamp, mediciones...)
    C->>A: GET /sensores/{id}
    A->>D: Query por device_id
    D-->>A: lecturas
    A-->>C: 200 JSON
```

## Estructura (simula tres repos independientes)

```
infraestructura/     # Terraform: bucket, tabla, lambdas publisher/ingestor, trigger
lambdas/             # Código de publisher e ingestor, tests, deploy.sh
api/                 # API REST con Chalice (NO usa Terraform; ver api/README.md)
Dockerfile           # Imagen de herramientas (AWS CLI, Terraform, Chalice, make, zip...)
GUIA-PASO-A-PASO.md  # Paso a paso desde el CMD de Windows (desplegar y probar en el Lab)
COMO-FUNCIONA.md     # Explicación detallada del código y de los servicios de AWS
Makefile             # Atajos
```

## Tipos de sensores

Las lambdas aceptan **cualquier tipo de sensor**. El id puede llamarse `device_id` o `sensor_id`, y el resto de campos se guarda tal cual:

```json
{"device_id": "sensor-01", "temperature": 23.5, "humidity": 60}
{"sensor_id": "ruido-01", "tipo": "ruido", "valor": 72.4}
```

`timestamp` es opcional (si no viene, se usa la hora actual en UTC). Si se invoca la publisher **solo con el id** (`make invoke`), genera una lectura simulada de temperatura y humedad.

---

# Cómo ejecutarlo

👉 **Sigue [GUIA-PASO-A-PASO.md](GUIA-PASO-A-PASO.md)**: explica todo desde el CMD de Windows (construir el contenedor, poner las keys del Learner Lab, desplegar, probar con evidencias y borrar).

📖 **Explicación detallada del código y de AWS: [COMO-FUNCIONA.md](COMO-FUNCIONA.md).**

En Windows no hace falta instalar `make`, AWS CLI, Terraform ni Chalice: todo corre dentro del contenedor `iot_dev_environment` (ver `Dockerfile`). Los comandos `make` se ejecutan **dentro** de ese contenedor.

## Referencia de comandos (dentro del contenedor)

| Comando | Qué hace |
|---|---|
| `make help` | Lista todos los comandos |
| `make test-all` | Pruebas locales de lambdas y API (moto, sin AWS) |
| `make infra-apply` / `make infra-destroy` | Crea / destruye la infraestructura (Terraform) |
| `make deploy` | Sube el código de las lambdas publisher e ingestor |
| `make invoke DEVICE=sensor-02` | Invoca la publisher directamente |
| `make scan` | Muestra la tabla `iot_lecturas` |
| `make api-deploy` / `make api-delete` | Despliega / elimina la API Chalice |
| `make api-url` / `make api-smoke` | URL de la API / prueba POST + GET |

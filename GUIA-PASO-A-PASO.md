# Guía paso a paso (sencilla): Pipeline IoT + API Chalice

Cada bloque dice **dónde** pegarlo:

- **📍 CMD** → el cmd de Windows (Windows + R → `cmd` → Enter).
- **📍 CONTENEDOR** → dentro del contenedor `iot_dev_environment` (la línea se ve `root@xxxx:/app#`).

Antes de todo: abre **Docker Desktop** y espera a que diga **Engine running**.

Qué vas a probar:

```
POST /eventos ─► API Chalice ─► Lambda publisher ─► S3 ─► Lambda ingestor ─► DynamoDB
GET /sensores/{id} ─► API Chalice ─► DynamoDB
```

---

# PREPARACIÓN (solo la primera vez)

## 1. Build docker image + crear el contenedor

📍 **CMD**

```bat
cd "C:\Users\JoseB\Desktop\7_lambda_with_dynamodb_with terraform"
docker build -t iot_dev_environment_image .
docker rm -f iot_dev_environment
docker run -d --name iot_dev_environment -v "%cd%:/app" iot_dev_environment_image
```
- El `build` tarda 2–5 minutos la primera vez.
- `docker rm -f` puede decir `No such container`: es normal (solo borra uno viejo si existía).
- La imagen trae Python 3.12, AWS CLI, Terraform, Chalice, make, zip, curl, jq y nano. **No necesitas instalar nada más en Windows.**

## 2. Entrar al contenedor

📍 **CMD**

```bat
docker exec -it iot_dev_environment bash
```
La línea cambia a `root@xxxx:/app#`. **Ya estás dentro.** (Para salir: `exit`.)

> Si reiniciaste el PC y dice que el contenedor no está corriendo:
> `docker start iot_dev_environment` y luego otra vez `docker exec -it iot_dev_environment bash`.

---

# PARTE A: probar en tu PC (sin AWS)

📍 **CONTENEDOR**

```bash
cd /app
make test-all
```
Debe terminar con `3 passed` (lambdas) y `22 passed` (API). 📸

Estas pruebas usan `moto` (AWS simulado en memoria): no gastan crédito ni necesitan keys.

---

# PARTE B: AWS

## 1. Launch Learner Lab

1. Abre **https://awsacademy.instructure.com** → **Cursos** → **AWS Academy Learner Lab** →
   **Módulos** → **Launch AWS Academy Learner Lab**.
2. Pulsa **Start Lab** y espera a que el círculo junto a **AWS** esté 🟢 verde.

## 2. Poner las keys de AWS en el contenedor

En el lab: **AWS Details** → **AWS CLI: Show**. Verás:
```
[default]
aws_access_key_id=...
aws_secret_access_key=...
aws_session_token=...
```

Para pegar en la terminal: clic derecho o **Ctrl + Shift + V**.

**2.1** Configura las keys:
📍 **CONTENEDOR**
```bash
aws configure
```
Contesta así (pega cada valor y Enter):
```
AWS Access Key ID:      <pega aws_access_key_id>
AWS Secret Access Key:  <pega aws_secret_access_key>
Default region name:    us-east-1
Default output format:  json
```

**2.2** Agrega el token de sesión (el del Learner Lab es obligatorio):
📍 **CONTENEDOR**
```bash
aws configure set aws_session_token <pega aws_session_token>
```
Pega el token completo **en una sola línea** (es muy largo; no importa).

**2.3** Test:
📍 **CONTENEDOR**
```bash
aws sts get-caller-identity
```
Debe mostrar tu `Account` y un `Arn` con `voclabs`. 📸
Si dice `ExpiredToken`, `InvalidClientTokenId` o `Unable to locate credentials`, repite 2.1, 2.2 y 2.3.

> **Cada vez que el lab se reinicia** (Start Lab de nuevo) las keys cambian:
> entra al contenedor (Preparación, paso 2) y repite **2.1**, **2.2** y **2.3**.

## 3. Validar Terraform

📍 **CONTENEDOR**

```bash
cd /app/infraestructura
terraform init
terraform fmt -check
terraform validate
cd /app
```
Debe decir `Terraform has been successfully initialized!` y `Success! The configuration is valid.` 📸
(`terraform fmt -check` no imprime nada si el formato está bien.)

## 4. Crear la infraestructura (bucket, tabla, lambdas, trigger)

📍 **CONTENEDOR**

```bash
cd /app
make infra-apply 2>&1 | tee salida-infra-apply.txt
```
Tarda 1–2 minutos. Debe terminar con `Apply complete! Resources: 6 added` y los `Outputs`
(`bucket_name = "iot-eventos-<tu cuenta>"`, `table_name = "iot_lecturas"`, ...). 📸
La salida queda en `salida-infra-apply.txt`.

## 5. Subir el código de las lambdas

📍 **CONTENEDOR**

```bash
cd /app
make deploy
```
Debe decir `iot_publisher_lambda desplegada` e `iot_ingestor_lambda desplegada`. 📸

## 6. Probar el flujo base (sin API)

📍 **CONTENEDOR**

```bash
cd /app
make invoke
sleep 5
make scan
```
- `invoke` muestra `"statusCode": 200` y la `key` del JSON en S3.
- `scan` muestra una fila de `sensor-01` con `temperature`, `humidity` y `s3_key`. 📸

## 7. Desplegar la API (Chalice)

📍 **CONTENEDOR**

```bash
cd /app
make api-deploy 2>&1 | tee salida-api-deploy.txt
```
Tarda 1–2 minutos. Al final muestra algo como:
```
Rest API URL: https://abc123.execute-api.us-east-1.amazonaws.com/api/
```
📸 (Chalice crea su propia lambda `iot-api-dev` y el API Gateway; **no** se toca Terraform.)

Comprobar que la API responde (debe decir `"estado": "ok"` y listar los endpoints):
📍 **CONTENEDOR**
```bash
curl -s $(make -s api-url) | jq
```
También puedes abrir esa URL en el navegador.

> Si ves `{"message": "Missing Authentication Token"}`: la API está desplegada, pero llamaste
> a una ruta o método que no existe (por ejemplo `GET /eventos`, que solo acepta **POST**).
> No es un problema de credenciales.

## 8. Probar la API y sacar capturas 📸

**8.1 Guardar la URL en una variable** (si sales del contenedor, repite este paso):
📍 **CONTENEDOR**
```bash
cd /app
URL=$(make -s api-url)
echo $URL
```

**8.2 POST de un sensor de temperatura** (📸, debe decir `"mensaje": "evento publicado"`):
📍 **CONTENEDOR**
```bash
curl -s -X POST ${URL}eventos -H 'Content-Type: application/json' \
  -d '{"device_id":"sensor-01","temperature":23.5,"humidity":60}' | jq
```

**8.3 POST de otro tipo de sensor (ruido)** (📸):
📍 **CONTENEDOR**
```bash
curl -s -X POST ${URL}eventos -H 'Content-Type: application/json' \
  -d '{"sensor_id":"ruido-01","tipo":"ruido","valor":72.4}' | jq
```

**8.4 Los JSON llegaron a S3** (📸, deben salir archivos en `events/sensor-01/` y `events/ruido-01/`):
📍 **CONTENEDOR**
```bash
BUCKET=$(terraform -chdir=infraestructura output -raw bucket_name)
aws s3 ls s3://$BUCKET/events/ --recursive
```

**8.5 Log de la lambda ingestor** (📸, debe salir `Insertado sensor-01 ...` e `Insertado ruido-01 ...`):
📍 **CONTENEDOR**
```bash
aws logs tail /aws/lambda/iot_ingestor_lambda --since 15m | grep Insertado
```

**8.6 GET: lecturas por sensor** (📸, las más recientes primero):
📍 **CONTENEDOR**
```bash
curl -s ${URL}sensores/sensor-01 | jq
curl -s "${URL}sensores/sensor-01?limit=1" | jq
curl -s ${URL}sensores/ruido-01 | jq
```

**8.7 Errores claros (400 / 415)** (📸 de cada `HTTP/... 400` y `415`):
📍 **CONTENEDOR**
```bash
# Body que no es JSON -> 400
curl -s -i -X POST ${URL}eventos -H 'Content-Type: application/json' -d 'no es json'; echo
# Sin id del sensor -> 400
curl -s -i -X POST ${URL}eventos -H 'Content-Type: application/json' -d '{"temperature":20}'; echo
# Sin mediciones -> 400
curl -s -i -X POST ${URL}eventos -H 'Content-Type: application/json' -d '{"device_id":"sensor-01"}'; echo
# limit inválido -> 400
curl -s -i "${URL}sensores/sensor-01?limit=abc"; echo
# Content-Type que no es JSON -> 415
curl -s -i -X POST ${URL}eventos -H 'Content-Type: text/plain' -d 'hola'; echo
```

**8.8 Tabla en DynamoDB** (📸, deben estar `sensor-01` y `ruido-01`):
📍 **CONTENEDOR**
```bash
make scan
```

**8.9 Navegador.** Copia la URL de 8.1, agrégale `sensores/sensor-01` y ábrela en el navegador
(ej. `https://abc123.execute-api.us-east-1.amazonaws.com/api/sensores/sensor-01`). 📸

**8.10 (Opcional) Consola de AWS.** En el lab pulsa **AWS** (🟢) y saca capturas de:
**Lambda** (`iot_publisher_lambda`, `iot_ingestor_lambda`, `iot-api-dev`), **S3** (bucket `iot-eventos-...`),
**DynamoDB** → `iot_lecturas` → *Explore items*, **API Gateway** → `iot-api`. 📸

> Prueba rápida de todo junto (POST + espera + GET): `make api-smoke`.

## 9. Borrar todo en AWS (para no gastar crédito)

**Primero la API, después la infraestructura.**

📍 **CONTENEDOR**

```bash
cd /app
make api-delete
make infra-destroy
```
`infra-destroy` pregunta `Enter a value:` → escribe `yes` y Enter. Debe terminar con `Destroy complete!`. 📸

Comprobar que no quedó nada (las 4 líneas deben salir **vacías**):
📍 **CONTENEDOR**
```bash
aws lambda list-functions --query "Functions[?starts_with(FunctionName,'iot')].FunctionName" --output text
aws dynamodb list-tables --query "TableNames[?starts_with(@,'iot')]" --output text
aws apigateway get-rest-apis --query "items[?name=='iot-api'].id" --output text
aws s3 ls | grep iot-eventos
```
Salir del contenedor:
📍 **CONTENEDOR**
```bash
exit
```

---

# LIMPIEZA: dejar el PC limpio

Antes: guarda tus capturas y copia `salida-infra-apply.txt` y `salida-api-deploy.txt` a otra carpeta.
**El paso 9 tiene que haber terminado bien**: si borras el estado de Terraform con recursos vivos en AWS,
después no podrás borrarlos con `make infra-destroy`.

📍 **CMD**

```bat
cd "C:\Users\JoseB\Desktop\7_lambda_with_dynamodb_with terraform"
docker rm -f iot_dev_environment
docker rmi iot_dev_environment_image
rmdir /s /q infraestructura\.terraform
del /q infraestructura\terraform.tfstate* infraestructura\.terraform.lock.hcl infraestructura\tfplan infraestructura\dummy.zip
rmdir /s /q api\.chalice\deployed api\.chalice\deployments
```
Borra el contenedor (con las keys que tenía dentro), su imagen y los archivos de estado de Terraform y
Chalice. **No** borra tu código ni los documentos. Algún comando puede decir
`No se encuentra el archivo`: es normal.

Por último, en el lab: **End Lab**.

La próxima vez empiezas otra vez desde **PREPARACIÓN, paso 1**.

---

## Si algo falla

| Lo que ves | Qué hacer |
|---|---|
| `"make" no se reconoce como un comando` | Lo pegaste en CMD; va en el CONTENEDOR (Preparación, paso 2). |
| `failed to connect to the docker API` | Docker Desktop no está abierto: ábrelo y espera **Engine running**. |
| `Conflict. The container name "/iot_dev_environment" is already in use` | Ya lo tienes creado: sáltate el paso 1 y ve al 2. |
| `No such container: iot_dev_environment` | Haz Preparación, paso 1. |
| `container ... is not running` | `docker start iot_dev_environment` y repite Preparación, paso 2. |
| `ExpiredToken` / `InvalidClientTokenId` / `Unable to locate credentials` | Repite 2.1, 2.2 y 2.3 (las tres keys deben ser de la misma sesión del lab). |
| `make deploy`: `la función iot_..._lambda no existe` | Falta el paso 4 (`make infra-apply`). |
| `make infra-apply`: `ResourceInUseException` / `already exists` | Quedaron recursos de otra sesión sin estado de Terraform: bórralos en la consola de AWS (Lambda `iot_*`, DynamoDB `iot_lecturas`, S3 `iot-eventos-*`) y repite el paso 4. |
| `echo $URL` sale vacío o `curl: (3) URL rejected` | No está desplegada la API (paso 7) o saliste del contenedor: repite 8.1. |
| `{"message": "Missing Authentication Token"}` (HTTP 403) | La ruta o el método no existen: `/eventos` es solo **POST** (con curl, no desde el navegador) y el GET es `/sensores/<id>`. Revisa que la URL termine en `/api/...`. |
| `POST /eventos` devuelve `502` | La publisher no existe o falló: revisa los pasos 4 y 5 y mira `aws logs tail /aws/lambda/iot_publisher_lambda --since 15m`. |
| `GET` devuelve `"cantidad": 0` justo después del POST | La ingestor es asíncrona: espera unos segundos y repite. Si sigue en 0, mira 8.5. |
| `chalice deploy`: `AccessDenied ... iam:CreateRole` | El `config.json` perdió `"manage_iam_role": false`; restáuralo y repite el paso 7. |

---

## Entregable (criterios del ToDo)

- [ ] `make test-all` → `3 passed` y `22 passed` (Parte A)
- [ ] `terraform validate` → Success (paso 3)
- [ ] `salida-infra-apply.txt` (paso 4) y `salida-api-deploy.txt` (paso 7)
- [ ] 📸 `POST /eventos` dispara la publisher y el dato aparece en DynamoDB (8.2 a 8.5 y 8.8)
- [ ] 📸 `GET /sensores/{id}` devuelve las lecturas del sensor (8.6 y 8.9)
- [ ] 📸 Respuestas de error claras: 400 y 415 (8.7)
- [ ] La API vive en `api/`, sin tocar `infraestructura/` (Terraform)
- [ ] `api/README.md` con ejemplos de `curl`
- [ ] `make api-delete` + `make infra-destroy` (paso 9) y limpieza

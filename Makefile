# Makefile del ejemplo IoT: S3 -> Lambda -> DynamoDB (+ API Chalice)
#
# En Windows se usa dentro del contenedor de herramientas:
#   docker compose run --rm tools make <comando>
VENV   := venv
REQS   := lambdas/requirements.txt
INFRA  := infraestructura
REGION := us-east-1
DEVICE ?= sensor-01

# Dentro del contenedor (IN_DOCKER=1) las dependencias ya están instaladas:
# se usa el Python del sistema y no se crea virtualenv.
ifeq ($(IN_DOCKER),1)
PY := python
else
PY := $(VENV)/bin/python
endif

# Para correr las lambdas en local contra AWS (bucket creado por Terraform)
LOCAL  := AWS_DEFAULT_REGION=$(REGION) BUCKET_NAME=$$(terraform -chdir=$(INFRA) output -raw bucket_name)

.PHONY: help venv test api-test test-all run-publisher run-ingestor infra-init infra-plan infra-apply \
        infra-destroy deploy invoke scan api-deploy api-url api-smoke api-delete clean

help:  ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

ifeq ($(IN_DOCKER),1)
venv:  # dentro del contenedor no hace falta virtualenv
	@true
else
venv: $(VENV)/bin/activate  ## Crea el virtualenv con lambdas/requirements.txt
$(VENV)/bin/activate: $(REQS)
	test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV)/bin/pip install -Ur $(REQS) -r api/requirements-dev.txt
	touch $(VENV)/bin/activate
endif

test: venv  ## Prueba las lambdas localmente (moto, sin tocar AWS)
	$(PY) -m pytest -v -p no:cacheprovider lambdas/tests

api-test: venv  ## Prueba la API localmente (Chalice test client + moto)
	$(PY) -m pytest -v -p no:cacheprovider api/tests

test-all: test api-test  ## Corre todas las pruebas locales

run-publisher: venv  ## Corre la publisher en local contra AWS (DEVICE=sensor-01)
	$(LOCAL) $(PY) lambdas/src/publisher/lambda_function.py $(DEVICE)

run-ingestor: venv  ## Corre la ingestor en local contra AWS (KEY=events/...json)
	@test -n "$(KEY)" || { echo "Falta KEY. Ej: make run-ingestor KEY=events/sensor-01/<uuid>.json"; exit 1; }
	$(LOCAL) $(PY) lambdas/src/ingestor/lambda_function.py $(KEY)

infra-init:  ## terraform init
	cd $(INFRA) && terraform init

infra-plan: infra-init  ## terraform plan
	cd $(INFRA) && terraform plan -out=tfplan

infra-apply: infra-plan  ## terraform plan + apply
	cd $(INFRA) && terraform apply tfplan

infra-destroy:  ## Destruye la infraestructura
	cd $(INFRA) && terraform destroy

deploy:  ## Despliega el código de ambas lambdas (lambdas/deploy.sh)
	bash lambdas/deploy.sh all

invoke:  ## Invoca la lambda publicadora en AWS (dispara todo el flujo)
	aws lambda invoke --function-name iot_publisher_lambda --region $(REGION) \
		--cli-binary-format raw-in-base64-out --payload '{"device_id":"$(DEVICE)"}' /dev/stdout

scan:  ## Muestra el contenido de la tabla iot_lecturas
	aws dynamodb scan --table-name iot_lecturas --region $(REGION) --output table

api-deploy:  ## Despliega la API con Chalice (api/deploy.sh)
	bash api/deploy.sh deploy

api-url:  ## Muestra la URL de la API desplegada
	@bash api/deploy.sh url

api-smoke:  ## Prueba la API desplegada: POST /eventos + GET /sensores/{id}
	@URL=$$(bash api/deploy.sh url); \
	echo "==> POST $${URL}eventos"; \
	curl -sS -X POST "$${URL}eventos" -H 'Content-Type: application/json' \
		-d '{"device_id":"$(DEVICE)","temperature":23.5,"humidity":60}'; echo; \
	echo "==> Esperando a que la ingestor guarde en DynamoDB..."; sleep 5; \
	echo "==> GET $${URL}sensores/$(DEVICE)?limit=3"; \
	curl -sS "$${URL}sensores/$(DEVICE)?limit=3"; echo

api-delete:  ## Elimina la API (lambda + API Gateway creados por Chalice)
	bash api/deploy.sh delete

clean:  ## Borra el virtualenv y caches
	rm -rf $(VENV) .pytest_cache lambdas/.pytest_cache api/.pytest_cache

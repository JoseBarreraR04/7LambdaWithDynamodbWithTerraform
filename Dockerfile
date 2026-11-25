# Imagen de herramientas para trabajar desde Windows sin instalar nada más
# que Docker Desktop. Trae: Python 3.12 (mismo runtime que las lambdas),
# AWS CLI v2, Terraform, make, zip, curl, jq y Chalice.
#
# Se usa a través de docker-compose.yml:
#   docker compose run --rm tools make help
FROM python:3.12-slim

ARG TERRAFORM_VERSION=1.9.8

RUN apt-get update \
 && apt-get install -y --no-install-recommends make zip unzip curl jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 y Terraform (descarga oficial según la arquitectura del equipo)
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64)  AWS_ARCH=x86_64;  TF_ARCH=amd64 ;; \
      aarch64) AWS_ARCH=aarch64; TF_ARCH=arm64 ;; \
      *) echo "Arquitectura no soportada: $(uname -m)"; exit 1 ;; \
    esac; \
    cd /tmp; \
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_ARCH}.zip" -o awscli.zip; \
    unzip -q awscli.zip; ./aws/install; \
    curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TF_ARCH}.zip" -o tf.zip; \
    unzip -q tf.zip -d /usr/local/bin; \
    rm -rf /tmp/*; \
    aws --version; terraform version

# Dependencias Python para pruebas locales y para desplegar la API
COPY lambdas/requirements.txt /tmp/req-lambdas.txt
COPY api/requirements-dev.txt /tmp/req-api.txt
RUN pip install --no-cache-dir -r /tmp/req-lambdas.txt -r /tmp/req-api.txt

# IN_DOCKER=1 hace que el Makefile use el Python del contenedor (sin venv)
ENV IN_DOCKER=1 \
    AWS_DEFAULT_REGION=us-east-1 \
    AWS_REGION=us-east-1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /work

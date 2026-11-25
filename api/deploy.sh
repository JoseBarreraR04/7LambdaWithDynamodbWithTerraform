#!/bin/bash
# Despliega (o elimina) la API con Chalice.
# Uso: ./deploy.sh [deploy|delete|url]
#
# En Learner Lab no se pueden crear roles IAM: la lambda de la API usa LabRole.
# Este script escribe en .chalice/config.json el ARN de LabRole de TU cuenta.
set -euo pipefail
cd "$(dirname "$0")"
STAGE="${STAGE:-dev}"

case "${1:-deploy}" in
  deploy)
    ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
    sed -i -E "s#arn:aws:iam::[^:]*:role/LabRole#arn:aws:iam::${ACCOUNT_ID}:role/LabRole#" .chalice/config.json
    echo "==> Usando rol arn:aws:iam::${ACCOUNT_ID}:role/LabRole"
    chalice deploy --stage "$STAGE"
    ;;
  delete) chalice delete --stage "$STAGE" ;;
  url)    chalice url --stage "$STAGE" ;;
  *) echo "Uso: $0 [deploy|delete|url]" >&2; exit 1 ;;
esac

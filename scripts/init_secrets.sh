#!/usr/bin/env bash
# init_secrets.sh — puebla el .env que lee pydantic-settings (config.py,
# env_prefix="SANTISIMA_", env_file=".env") a partir de un secrets manager.
#
# No cambia nada en config.py ni en el resto del código: es puramente
# operacional. Escribe un archivo .env en el directorio del proyecto (raíz
# del repo, o $ENV_FILE si se pasa) con las mismas variables que hoy se
# escriben a mano en desarrollo local, para que Settings las lea exactamente
# igual sin importar de dónde vinieron.
#
# Modos:
#   --mode local  (default)  Desarrollo local. No toca secretos reales: solo
#                             garantiza que exista un .env (copiándolo de
#                             .env.example si falta) y termina. Nunca
#                             sobrescribe un .env existente.
#   --mode aws                Producción vía AWS Secrets Manager. Lee UN
#                             secreto (JSON) con `aws secretsmanager
#                             get-secret-value` y escribe sus claves como
#                             variables de entorno en .env.
#   --mode vault               Producción vía HashiCorp Vault. Lee UNA ruta
#                             KV (`vault kv get -format=json`) y escribe sus
#                             claves como variables de entorno en .env.
#
# Uso típico en el paso de deploy, antes de arrancar uvicorn:
#   scripts/init_secrets.sh --mode aws
#   uvicorn la_santisima_conversacional.presentation.http_api:app ...
#
# Variables de entorno que controlan el script (todas tienen default):
#   ENV_FILE              Ruta del .env a escribir. Default: ./.env
#   AWS_SECRET_NAME        Nombre del secreto en AWS Secrets Manager.
#                          Default: la-santisima/prod
#   AWS_REGION             Región de AWS. Default: usa la config/entorno de
#                          la AWS CLI (AWS_DEFAULT_REGION, ~/.aws/config).
#   VAULT_KV_PATH           Ruta KV en Vault. Default: secret/la-santisima/prod
#
# Nunca imprime valores de secretos a stdout/stderr/logs: solo nombres de
# claves y conteos.
set -euo pipefail

MODE="local"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

AWS_SECRET_NAME="${AWS_SECRET_NAME:-la-santisima/prod}"
VAULT_KV_PATH="${VAULT_KV_PATH:-secret/la-santisima/prod}"

# Claves requeridas dentro del blob JSON (AWS) o del KV (Vault). Estos son
# los mismos nombres de variable que Settings/pydantic-settings esperan en
# el entorno: DEEPINFRA_API_KEY sin prefijo (identifica al proveedor, no a
# esta app), el resto con prefijo SANTISIMA_ (ver config.py).
REQUIRED_KEYS=(
    "DEEPINFRA_API_KEY"
    "SANTISIMA_CLAVE_CIFRADO"
    "SANTISIMA_SESSION_SECRET"
    "SANTISIMA_POSTGRES_DSN"
    "SANTISIMA_REDIS_URL"
)

err() {
    echo "init_secrets.sh: ERROR: $*" >&2
}

info() {
    echo "init_secrets.sh: $*"
}

usage() {
    cat >&2 <<'EOF'
Uso: scripts/init_secrets.sh [--mode local|aws|vault]

  --mode local   (default) Desarrollo local: crea .env desde .env.example
                 si no existe. No toca secretos reales.
  --mode aws     Producción: lee el secreto JSON de AWS Secrets Manager
                 (ver AWS_SECRET_NAME) y escribe .env.
  --mode vault   Producción: lee la ruta KV de Vault (ver VAULT_KV_PATH)
                 y escribe .env.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="${2:-}"
            shift 2
            ;;
        --mode=*)
            MODE="${1#--mode=}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            err "argumento desconocido: $1"
            usage
            exit 1
            ;;
    esac
done

case "$MODE" in
    local|aws|vault) ;;
    *)
        err "--mode inválido: '$MODE' (usar local, aws o vault)"
        exit 1
        ;;
esac

# --- Modo local: comportamiento actual, no destructivo ---------------------
init_local() {
    if [[ -f "$ENV_FILE" ]]; then
        info "modo local: $ENV_FILE ya existe, no se toca."
        exit 0
    fi
    if [[ ! -f "$ENV_EXAMPLE" ]]; then
        err "modo local: no existe $ENV_FILE ni $ENV_EXAMPLE; nada que copiar."
        exit 1
    fi
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    info "modo local: $ENV_FILE creado a partir de .env.example. Complétalo con tus valores de desarrollo."
    exit 0
}

# --- Escritura común: JSON de claves -> archivo .env ------------------------
# Recibe el JSON completo por stdin. Valida que estén todas las REQUIRED_KEYS
# (falla si falta alguna, en vez de escribir una variable vacía), y escribe
# TODAS las claves presentes en el JSON (permite claves opcionales extra,
# p. ej. SANTISIMA_API_KEYS) como líneas KEY=value en $ENV_FILE.
write_env_from_json() {
    local json="$1"
    local tmp_file
    tmp_file="$(mktemp)"

    local faltantes=()
    for key in "${REQUIRED_KEYS[@]}"; do
        local presente
        presente="$(printf '%s' "$json" | jq -r --arg k "$key" 'has($k) and (.[$k] != null) and (.[$k] != "")')"
        if [[ "$presente" != "true" ]]; then
            faltantes+=("$key")
        fi
    done

    if [[ "${#faltantes[@]}" -gt 0 ]]; then
        rm -f "$tmp_file"
        err "faltan claves requeridas en el secreto: ${faltantes[*]}"
        err "no se escribe $ENV_FILE (no se usan valores vacíos para un secreto de producción)."
        exit 1
    fi

    {
        echo "# Generado por scripts/init_secrets.sh (--mode $MODE). No editar a mano."
        echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf '%s\n' "$json" | jq -r 'to_entries[] | "\(.key)=\(.value)"'
    } > "$tmp_file"

    local n_claves
    n_claves="$(printf '%s\n' "$json" | jq 'keys | length')"

    install -m 600 "$tmp_file" "$ENV_FILE"
    rm -f "$tmp_file"
    info "$MODE: $ENV_FILE escrito con $n_claves claves (valores no impresos)."
}

# --- Modo aws ---------------------------------------------------------------
init_aws() {
    if ! command -v aws >/dev/null 2>&1; then
        err "aws-cli no encontrado en PATH. Instálalo (https://docs.aws.amazon.com/cli/) antes de usar --mode aws."
        exit 1
    fi
    if ! command -v jq >/dev/null 2>&1; then
        err "jq no encontrado en PATH (requerido para parsear el secreto). Instálalo."
        exit 1
    fi

    local secret_json
    local aws_args=(secretsmanager get-secret-value --secret-id "$AWS_SECRET_NAME" --query SecretString --output text)
    if [[ -n "${AWS_REGION:-}" ]]; then
        aws_args+=(--region "$AWS_REGION")
    fi

    local aws_err_file
    aws_err_file="$(mktemp)"
    if ! secret_json="$(aws "${aws_args[@]}" 2>"$aws_err_file")"; then
        err "no se pudo leer el secreto '$AWS_SECRET_NAME' de AWS Secrets Manager."
        err "$(tail -n 5 "$aws_err_file" 2>/dev/null | sed 's/^/  /')"
        rm -f "$aws_err_file"
        exit 1
    fi
    rm -f "$aws_err_file"

    if [[ -z "$secret_json" ]]; then
        err "el secreto '$AWS_SECRET_NAME' está vacío."
        exit 1
    fi

    if ! printf '%s' "$secret_json" | jq empty >/dev/null 2>&1; then
        err "el secreto '$AWS_SECRET_NAME' no es JSON válido (se espera un objeto plano clave: valor)."
        exit 1
    fi

    write_env_from_json "$secret_json"
}

# --- Modo vault --------------------------------------------------------------
init_vault() {
    if ! command -v vault >/dev/null 2>&1; then
        err "vault CLI no encontrado en PATH. Instálalo (https://developer.hashicorp.com/vault/install) antes de usar --mode vault."
        exit 1
    fi
    if ! command -v jq >/dev/null 2>&1; then
        err "jq no encontrado en PATH (requerido para parsear el secreto). Instálalo."
        exit 1
    fi
    # Requiere VAULT_ADDR/VAULT_TOKEN (u otro método de auth) ya configurados
    # en el entorno, igual que cualquier otro uso de la vault CLI.
    if [[ -z "${VAULT_ADDR:-}" ]]; then
        err "VAULT_ADDR no está configurado en el entorno."
        exit 1
    fi

    local kv_json
    local vault_err_file
    vault_err_file="$(mktemp)"
    if ! kv_json="$(vault kv get -format=json "$VAULT_KV_PATH" 2>"$vault_err_file")"; then
        err "no se pudo leer la ruta KV '$VAULT_KV_PATH' de Vault."
        err "$(tail -n 5 "$vault_err_file" 2>/dev/null | sed 's/^/  /')"
        rm -f "$vault_err_file"
        exit 1
    fi
    rm -f "$vault_err_file"

    # KV v2: los datos están en .data.data; KV v1: en .data. Se intenta v2
    # primero y se cae a v1 si .data.data no existe.
    local secret_json
    secret_json="$(printf '%s' "$kv_json" | jq -c 'if (.data.data // null) != null then .data.data else .data end')"

    if [[ -z "$secret_json" || "$secret_json" == "null" ]]; then
        err "no se encontraron datos en '$VAULT_KV_PATH' (respuesta de Vault sin .data/.data.data)."
        exit 1
    fi

    write_env_from_json "$secret_json"
}

case "$MODE" in
    local) init_local ;;
    aws) init_aws ;;
    vault) init_vault ;;
esac

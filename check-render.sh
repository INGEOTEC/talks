#!/usr/bin/env bash
# Renders the whole Quarto site locally so errors can be caught before a
# commit/push (unlike render.sh, this script never touches gh-pages).
#
# Usage: ./check-render.sh

set -u -o pipefail

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

if ! command -v quarto >/dev/null 2>&1; then
    echo "quarto no esta instalado o no esta en el PATH." >&2
    exit 1
fi

ENV_NAME=$(grep -m1 '^name:' environment.yml 2>/dev/null | sed 's/name: *//')
if [ -n "${ENV_NAME:-}" ] && [ "${CONDA_DEFAULT_ENV:-}" != "$ENV_NAME" ]; then
    echo "Aviso: el entorno conda activo es '${CONDA_DEFAULT_ENV:-ninguno}', se esperaba '$ENV_NAME'."
    echo "       Algunas celdas de Python (EvoMSA, microtc, encexp, dialectid, ...) pueden fallar por dependencias faltantes."
    echo "       Activalo con: conda env create -f environment.yml && conda activate $ENV_NAME"
    echo
fi

# Empezar de un estado limpio: una carpeta _site o cache .quarto de una
# corrida anterior puede dejar symlinks de recursos a medio crear, lo que
# hace fallar el render con errores como "AlreadyExists" al copiar imagenes
# que comparten el mismo nombre en dos carpetas distintas del proyecto.
rm -rf _site .quarto

echo "Renderizando el sitio completo (esto puede tardar varios minutos)..."
quarto render . 2>&1 | tee "$LOG"
RENDER_STATUS=$?

echo
echo "-------------------------------------------------------------"

FATAL=$(grep -E "ERROR:|Quitting from|Execution halted|An error occurred while executing" "$LOG")
WARNINGS=$(grep -E "\[WARNING\]|WARN:" "$LOG")

if [ -n "$FATAL" ] || [ "$RENDER_STATUS" != "0" ]; then
    echo "Render FALLIDO. Resumen de errores:"
    echo "$FATAL"
    echo
    echo "Revisa el log completo arriba, corrige los .qmd/recursos senalados"
    echo "y vuelve a correr 'sh check-render.sh' antes de hacer commit."
    exit 1
fi

if [ -n "$WARNINGS" ]; then
    echo "Render OK, pero con advertencias que conviene revisar:"
    echo "$WARNINGS"
    echo
fi

echo "Render OK. Previsualiza el resultado con:"
echo "  quarto preview ."
echo "(_site/ no se commitea, esta en .gitignore)"

#!/usr/bin/env bash
# Instala/atualiza o lançador de rede no perfil do usuário e inicia a interface interativa.
set -euo pipefail

REPO_NAME="Script_para_subir_maquinas_10.42"
REPO_URL="https://github.com/Lucasuimaraes/Script_para_subir_maquinas_10.42.git"
BRANCH=main

if (( EUID == 0 )); then
    printf 'Execute como usuário normal, sem sudo. O instalador pedirá sudo apenas para instalar dependências.\n' >&2
    exit 2
fi
if [[ -z ${HOME:-} || ! -d $HOME ]]; then
    printf 'Não foi possível localizar a pasta pessoal do usuário.\n' >&2
    exit 2
fi
command -v sudo >/dev/null 2>&1 || { printf 'O comando sudo não está disponível neste Linux Mint.\n' >&2; exit 2; }

DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
[[ $DATA_HOME == /* ]] || DATA_HOME="$HOME/.local/share"
INSTALL_DIR="$DATA_HOME/ironvox/$REPO_NAME"

if [[ -L $INSTALL_DIR ]]; then
    printf 'A pasta de instalação é um link simbólico; revise: %s\n' "$INSTALL_DIR" >&2
    exit 2
fi
if [[ -e $INSTALL_DIR && ! -d $INSTALL_DIR/.git ]]; then
    printf 'Já existe uma pasta que não é um clone Git: %s\nRemova ou renomeie essa pasta e tente novamente.\n' "$INSTALL_DIR" >&2
    exit 2
fi
if [[ -d $INSTALL_DIR/.git ]]; then
    origin=$(git -C "$INSTALL_DIR" remote get-url origin)
    if [[ ${origin%.git} != ${REPO_URL%.git} ]]; then
        printf 'O clone existente aponta para outro repositório: %s\n' "$origin" >&2
        exit 2
    fi
fi

printf 'Instalando dependências necessárias (sem atualizar as fontes do APT)...\n'
sudo apt-get install -y git ca-certificates python3 python3-paramiko iputils-ping

mkdir -p "$(dirname -- "$INSTALL_DIR")"
if [[ -d $INSTALL_DIR/.git ]]; then
    printf 'Atualizando projeto em %s...\n' "$INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
else
    printf 'Baixando projeto em %s...\n' "$INSTALL_DIR"
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
fi

[[ -f $INSTALL_DIR/subir-maquinas.py && -f $INSTALL_DIR/ironvox-remoto.py ]] || { printf 'Arquivos do instalador incompletos em %s.\n' "$INSTALL_DIR" >&2; exit 1; }
printf 'Abrindo o instalador interativo...\n'
exec python3 "$INSTALL_DIR/subir-maquinas.py"

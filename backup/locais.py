"""Onde ficam os arquivos do programa, rodando pelo código ou pelo executável.

Pelo código (iniciar.bat), tudo fica na pasta do projeto.
Pelo executável, os recursos vêm de dentro dele e o que o programa grava
(configuração, registros, ADB) vai para a pasta de dados do usuário no Windows.
"""
import os
import shutil
import sys
from pathlib import Path

NOME = "Backup Corporativo"
EXECUTAVEL = bool(getattr(sys, "frozen", False))
PROJETO = Path(__file__).resolve().parent.parent

if EXECUTAVEL:
    RECURSOS = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DADOS = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / NOME
else:
    RECURSOS = PROJETO
    DADOS = PROJETO

CONFIG = DADOS / "config.json"
REGISTROS = DADOS / "registros"
NOMES_DE_APPS = DADOS / "nomes_apps.json"
ICONE = RECURSOS / "recursos" / "icone.ico"
_ADB_EMBUTIDO = RECURSOS / "platform-tools"
_ADB_DO_PROJETO = PROJETO / "tools" / "platform-tools"


def adb():
    """Caminho do adb.exe. No executável ele é copiado uma vez para a pasta de dados.

    Rodar o ADB de dentro do executável não serve: ele fica ligado depois que o
    programa fecha e travaria a pasta temporária de onde o executável roda.
    """
    if not EXECUTAVEL:
        return _ADB_DO_PROJETO / "adb.exe"
    destino = DADOS / "platform-tools"
    origem = _ADB_EMBUTIDO / "adb.exe"
    instalado = destino / "adb.exe"
    try:
        if origem.exists() and (
            not instalado.exists() or instalado.stat().st_size != origem.stat().st_size
        ):
            destino.mkdir(parents=True, exist_ok=True)
            for arquivo in _ADB_EMBUTIDO.iterdir():
                shutil.copy2(arquivo, destino / arquivo.name)
    except OSError:
        pass  # ADB em uso por outra janela do programa: usa o que já está lá
    return instalado


def preparar():
    DADOS.mkdir(parents=True, exist_ok=True)

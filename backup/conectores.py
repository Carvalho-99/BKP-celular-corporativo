"""Aparelhos ligados ao computador, de qualquer plataforma.

Android e iPhone compartilham a tela, os relatórios e os estados, mas cada um
tem o próprio jeito de ser detectado, identificado e copiado.
"""
import json
import subprocess
from dataclasses import dataclass

from . import adb, captura, cobertura, executar
from .leitura import GRUPO_APARELHO, GRUPO_USUARIO, NAO_IMPLEMENTADO, Registro

ANDROID = "Android"
IPHONE = "iPhone"

PRONTO = "pronto"  # autorizado, pode identificar
AUTORIZAR = "autorizar"  # detectado, falta aceitar no aparelho
SEM_RESPOSTA = "sem_resposta"
SEM_SUPORTE = "sem_suporte"  # detectado, mas o programa ainda não sabe copiar

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_APPLE = "05AC"  # código da Apple no USB
MOTIVO_IPHONE = (
    "O backup de iPhone ainda não foi implementado nesta versão. O aparelho é reconhecido "
    "no cabo, mas nenhuma informação é lida e nada é copiado."
)


@dataclass
class Aparelho:
    plataforma: str
    id: str  # número de série do ADB, ou identificador USB no iPhone
    estado: str
    modelo: str = ""
    detalhe: str = ""

    @property
    def rotulo(self):
        return f"{self.modelo or self.plataforma} ({self.id})"


def listar(com_iphone=True):
    """Todos os aparelhos no cabo. Levanta adb.AdbErro se o ADB não puder ser usado."""
    aparelhos = []
    for a in adb.listar_aparelhos():
        estado = {"device": PRONTO, "unauthorized": AUTORIZAR}.get(a["estado"], SEM_RESPOSTA)
        aparelhos.append(Aparelho(ANDROID, a["serial"], estado, a["modelo"], a["estado"]))
    if com_iphone:
        aparelhos += listar_iphones()
    return aparelhos


def listar_iphones():
    """iPhones e iPads que o Windows enxerga no USB. Não depende de nenhum programa da Apple."""
    comando = (
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.InstanceId -like 'USB\\VID_{_APPLE}&PID_12*' -and $_.InstanceId -notlike '*&MI_*' }} | "
        "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
            capture_output=True, timeout=20, creationflags=_SEM_JANELA,
        )
        return interpretar_iphones(r.stdout.decode("utf-8", errors="replace"))
    except (OSError, subprocess.TimeoutExpired):
        return []  # sem essa consulta o Android continua funcionando


def interpretar_iphones(saida):
    saida = saida.strip()
    if not saida:
        return []
    try:
        itens = json.loads(saida)
    except ValueError:
        return []
    if isinstance(itens, dict):
        itens = [itens]
    aparelhos = {}
    for item in itens:
        identificador = str(item.get("InstanceId", "")).rsplit("\\", 1)[-1]
        if identificador:
            nome = item.get("FriendlyName") or "Aparelho Apple"
            aparelhos[identificador] = Aparelho(IPHONE, identificador, SEM_SUPORTE, nome, MOTIVO_IPHONE)
    return list(aparelhos.values())


def identificar(aparelho, ler_tela=True):
    if aparelho.plataforma == ANDROID:
        return captura.identificar(aparelho.id, ler_tela=ler_tela)
    return _identificar_iphone(aparelho)


def _identificar_iphone(aparelho):
    registro = Registro(f"iPhone {aparelho.id}")
    registro.coletado(GRUPO_APARELHO, "Nome informado pelo Windows", aparelho.modelo, "dispositivos USB do Windows")
    registro.coletado(
        GRUPO_APARELHO, "Identificador USB", aparelho.id,
        "dispositivos USB do Windows (não é o IMEI nem o número de série da etiqueta)",
    )
    for grupo, item in (
        (GRUPO_APARELHO, "Modelo, versão do iOS e número de série"),
        (GRUPO_APARELHO, "IMEI, linha e operadora"),
        (GRUPO_APARELHO, "Armazenamento e bateria"),
        (GRUPO_USUARIO, "Nome do aparelho e conta Apple"),
        (GRUPO_USUARIO, "Aplicativos instalados"),
    ):
        registro.anotar(
            grupo, item, NAO_IMPLEMENTADO, metodo="conector de iPhone",
            motivo="a leitura de iPhone ainda não foi implementada nesta versão",
        )
    resultado = captura.Identificacao(IPHONE, aparelho.id, aparelho.modelo or "iPhone", registro.leituras)
    resultado.registro_em = registro.gravar()
    return resultado


def levantar_cobertura(aparelho):
    if aparelho.plataforma == ANDROID:
        return cobertura.android(aparelho.id)
    return {
        chave: cobertura.Cobertura(
            chave, cobertura.INDISPONIVEL, "iPhone: ainda não implementado", inacessivel=MOTIVO_IPHONE
        )
        for chave in cobertura.CATEGORIAS
    }


def motivo_para_nao_copiar(aparelho):
    """Texto do impedimento, ou "" se o backup deste aparelho pode rodar."""
    return MOTIVO_IPHONE if aparelho.plataforma == IPHONE else ""


def fazer_backup(aparelho, dados, opcoes, destino, tela):
    if aparelho.plataforma != ANDROID:
        raise NotImplementedError(MOTIVO_IPHONE)
    return executar.rodar(aparelho.id, dados, opcoes, destino, tela)

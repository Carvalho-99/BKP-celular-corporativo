"""Camada fina em volta do adb.exe que vem na pasta tools/."""
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ADB = RAIZ / "tools" / "platform-tools" / "adb.exe"

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AdbErro(Exception):
    pass


def _base(serial):
    return [str(ADB)] + (["-s", serial] if serial else [])


def executar(args, serial=None, timeout=60):
    """Roda um comando adb e devolve a saída como texto."""
    try:
        r = subprocess.run(
            _base(serial) + list(args),
            capture_output=True,
            timeout=timeout,
            creationflags=_SEM_JANELA,
        )
    except subprocess.TimeoutExpired:
        raise AdbErro(f"O celular demorou demais para responder ({' '.join(args)[:60]})")
    except FileNotFoundError:
        raise AdbErro(f"adb.exe não encontrado em {ADB}")
    saida = r.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if r.returncode != 0 and not saida.strip():
        erro = r.stderr.decode("utf-8", errors="replace").strip()
        if erro:
            raise AdbErro(erro)
    return saida


def shell(comando, serial, timeout=60):
    return executar(["shell", comando], serial, timeout)


@dataclass
class Resposta:
    saida: str
    erro: str  # o que o comando escreveu no canal de erro (é onde o Android avisa "acesso negado")
    codigo: int

    @property
    def tudo(self):
        return f"{self.erro}\n{self.saida}"


# mensagens do próprio adb quando o problema é o cabo ou a autorização, não o comando
_SEM_COMUNICACAO = ("device offline", "device unauthorized", "no devices", "not found", "device still")


def consultar(comando, serial, timeout=60):
    """Roda um comando no celular e devolve saída, erro e código, sem esconder nada.

    Só levanta AdbErro quando não houve comunicação com o aparelho.
    """
    try:
        r = subprocess.run(
            _base(serial) + ["shell", comando],
            capture_output=True,
            timeout=timeout,
            creationflags=_SEM_JANELA,
        )
    except subprocess.TimeoutExpired:
        raise AdbErro(f"o celular não respondeu em {timeout}s")
    except FileNotFoundError:
        raise AdbErro(f"adb.exe não encontrado em {ADB}")
    saida = r.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    erro = r.stderr.decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
    primeira = erro.splitlines()[0].lower() if erro else ""
    if r.returncode != 0 and primeira.startswith(("adb", "error:")) and any(
        m in primeira for m in _SEM_COMUNICACAO
    ):
        raise AdbErro(erro.splitlines()[0])
    return Resposta(saida, erro, r.returncode)


def stream(comando, serial):
    """Abre um comando no celular devolvendo a saída binária crua (sem conversão)."""
    return subprocess.Popen(
        _base(serial) + ["exec-out", comando],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1024 * 1024,
        creationflags=_SEM_JANELA,
    )


def aspas(texto):
    """Protege um caminho para uso no shell do Android."""
    return shlex.quote(texto)


def listar_aparelhos():
    """Devolve [{serial, estado, modelo}] dos aparelhos ligados no cabo."""
    aparelhos = []
    for linha in executar(["devices", "-l"], timeout=30).splitlines()[1:]:
        partes = linha.split()
        if len(partes) < 2:
            continue
        extras = dict(p.split(":", 1) for p in partes[2:] if ":" in p)
        aparelhos.append(
            {
                "serial": partes[0],
                "estado": partes[1],
                "modelo": extras.get("model", "").replace("_", " "),
            }
        )
    return aparelhos

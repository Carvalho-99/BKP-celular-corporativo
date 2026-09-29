"""Cópia dos arquivos do celular em fluxo único (tar), com manifesto de integridade."""
import errno
import hashlib
import os
import re
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import adb

ARMAZENAMENTO = "/sdcard"
# da pasta Android só entram media (onde fica o WhatsApp) e data (arquivos externos dos apps);
# obb são arquivos de jogos, sem dado do usuário
_PULAR_NA_RAIZ = {"Android"}
_DENTRO_DE_ANDROID = ("Android/media", "Android/data")
_BLOCO = 1024 * 1024

_INVALIDOS = re.compile(r'[<>:"|?*\\\x00-\x1f]')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


class Cancelado(Exception):
    pass


@dataclass
class Resultado:
    origem: str
    arquivos: int = 0
    bytes: int = 0
    esperados: int = 0
    falhas: list = field(default_factory=list)
    erro: str = ""

    @property
    def completo(self):
        return not self.erro and not self.falhas and self.arquivos >= self.esperados


def longo(caminho):
    r"""Prefixo \\?\ para passar do limite de 260 caracteres do Windows."""
    texto = os.path.abspath(str(caminho))
    if texto.startswith("\\\\?\\"):
        return texto
    if texto.startswith("\\\\"):
        return "\\\\?\\UNC\\" + texto[2:]
    return "\\\\?\\" + texto


def _limpar(parte):
    parte = _INVALIDOS.sub("_", parte).rstrip(". ") or "_"
    if parte.split(".")[0].upper() in _RESERVADOS:
        parte = "_" + parte
    return parte


def caminho_seguro(nome, usados):
    """Converte o caminho do Android em um caminho válido e único no Windows."""
    partes = [_limpar(p) for p in nome.split("/") if p not in ("", ".", "..")]
    if not partes:
        return None
    base = Path(*partes)
    relativo, n = base, 1
    while str(relativo).lower() in usados:
        n += 1
        relativo = base.with_name(f"{base.stem} ({n}){base.suffix}")
    usados.add(str(relativo).lower())
    return relativo


def origens(serial, tudo=True, extras=()):
    """Caminhos (relativos a /sdcard) que serão copiados."""
    lista = []
    if tudo:
        nomes = adb.shell(f"ls -1A {ARMAZENAMENTO}/", serial).splitlines()
        lista = [n.strip() for n in nomes if n.strip() and n.strip() not in _PULAR_NA_RAIZ]
        lista += [pasta for pasta in _DENTRO_DE_ANDROID if existe(serial, pasta)]
    for extra in extras:
        dentro = any(extra == o or extra.startswith(o + "/") for o in lista)
        if not dentro and existe(serial, extra):
            lista.append(extra)
    return lista


def existe(serial, relativo):
    caminho = adb.aspas(f"{ARMAZENAMENTO}/{relativo}")
    return adb.shell(f"[ -e {caminho} ] && echo sim", serial).strip() == "sim"


def tamanho(serial, relativo):
    caminho = adb.aspas(f"{ARMAZENAMENTO}/{relativo}")
    saida = adb.shell(f"du -sk {caminho} 2>/dev/null", serial, timeout=600).split()
    return int(saida[0]) * 1024 if saida and saida[0].isdigit() else 0


def tamanho_de(serial, relativos):
    """Soma de várias pastas em uma consulta só, para a verificação antes do backup."""
    caminhos = " ".join(adb.aspas(f"{ARMAZENAMENTO}/{r}") for r in relativos)
    saida = adb.shell(f"du -sk {caminhos} 2>/dev/null", serial, timeout=600)
    return sum(int(l.split()[0]) for l in saida.splitlines() if l.split() and l.split()[0].isdigit()) * 1024


def contar(serial, relativo):
    caminho = adb.aspas(f"{ARMAZENAMENTO}/{relativo}")
    saida = adb.shell(f"find {caminho} -type f 2>/dev/null | wc -l", serial, timeout=600).strip()
    return int(saida) if saida.isdigit() else 0


def tem_tar(serial):
    return bool(adb.shell("command -v tar", serial).strip())


def extrair(fluxo, destino, resultado, manifesto, ao_copiar, cancelado, usados):
    """Lê o tar vindo do celular e grava arquivo por arquivo calculando o SHA-256."""
    try:
        with tarfile.open(fileobj=fluxo, mode="r|") as tar:
            for membro in tar:
                if cancelado():
                    raise Cancelado()
                if not membro.isfile():
                    continue
                relativo = caminho_seguro(membro.name, usados)
                if relativo is None:
                    continue
                try:
                    sha = _gravar(tar.extractfile(membro), destino / relativo, membro.mtime, ao_copiar)
                except OSError as e:
                    if e.errno == errno.ENOSPC:
                        raise
                    resultado.falhas.append(f"{membro.name}: {e.strerror or e}")
                    continue
                resultado.arquivos += 1
                resultado.bytes += membro.size
                manifesto.writerow(
                    [
                        str(relativo),
                        membro.size,
                        sha,
                        datetime.fromtimestamp(membro.mtime).strftime("%d/%m/%Y %H:%M:%S"),
                    ]
                )
    except OSError as e:
        if e.errno == errno.ENOSPC:
            resultado.erro = "Acabou o espaço no disco de destino"
        else:
            resultado.erro = f"Falha de leitura/gravação: {e}"
    except (tarfile.TarError, EOFError) as e:
        resultado.erro = f"Cópia interrompida: {e}"


def _gravar(origem, caminho, mtime, ao_copiar):
    os.makedirs(longo(caminho.parent), exist_ok=True)
    sha = hashlib.sha256()
    with open(longo(caminho), "wb") as saida:
        while True:
            bloco = origem.read(_BLOCO)
            if not bloco:
                break
            saida.write(bloco)
            sha.update(bloco)
            ao_copiar(len(bloco))
    os.utime(longo(caminho), (mtime, mtime))
    return sha.hexdigest()


def copiar(serial, relativo, destino, manifesto, ao_copiar, cancelado, usados, usar_tar=True):
    resultado = Resultado(origem=relativo, esperados=contar(serial, relativo))
    if usar_tar:
        _copiar_tar(serial, relativo, destino, resultado, manifesto, ao_copiar, cancelado, usados)
    else:
        _copiar_pull(serial, relativo, destino, resultado, manifesto, ao_copiar)
    return resultado


def _copiar_tar(serial, relativo, destino, resultado, manifesto, ao_copiar, cancelado, usados):
    alvo = adb.aspas("./" + relativo)
    processo = adb.stream(f"cd {ARMAZENAMENTO} && tar -cf - {alvo} 2>/dev/null", serial)
    try:
        extrair(processo.stdout, destino, resultado, manifesto, ao_copiar, cancelado, usados)
    finally:
        processo.kill()
        processo.wait()


def _copiar_pull(serial, relativo, destino, resultado, manifesto, ao_copiar):
    """Plano B para aparelhos antigos sem tar: adb pull, mais lento."""
    alvo = destino / Path(*PurePosixPath(relativo).parts)
    os.makedirs(longo(alvo.parent), exist_ok=True)
    try:
        adb.executar(["pull", "-a", f"{ARMAZENAMENTO}/{relativo}", str(alvo)], serial, timeout=None)
    except adb.AdbErro as e:
        resultado.erro = str(e)
    arquivos = [alvo] if alvo.is_file() else [p for p in alvo.rglob("*") if p.is_file()]
    for arquivo in arquivos:
        sha = hashlib.sha256()
        with open(longo(arquivo), "rb") as f:
            for bloco in iter(lambda: f.read(_BLOCO), b""):
                sha.update(bloco)
        info = os.stat(longo(arquivo))
        ao_copiar(info.st_size)
        resultado.arquivos += 1
        resultado.bytes += info.st_size
        manifesto.writerow(
            [
                str(arquivo.relative_to(destino)),
                info.st_size,
                sha.hexdigest(),
                datetime.fromtimestamp(info.st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
            ]
        )

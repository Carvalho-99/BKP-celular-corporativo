"""Descobre o nome comercial de um app a partir do pacote (com.whatsapp -> WhatsApp).

O Android não entrega o nome pelo cabo, então consulta a página pública do app
na Play Store. Só o nome do pacote é enviado. O resultado fica guardado em
nomes_apps.json para não consultar de novo.
"""
import html
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "nomes_apps.json"
CONSULTAR_PLAY_STORE = True

_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL)
_SUFIXO = re.compile(r"\s+[–-]\s+Apps (no|on) Google Play\s*$")
_GENERICOS = {
    "com", "br", "org", "net", "io", "co", "gov", "android", "app", "apps", "mobile", "www",
    "sec", "google", "client", "main",
}


def nome_provavel(pacote):
    """Palpite pelo próprio pacote, usado quando a Play Store não conhece o app."""
    partes = [p for p in pacote.split(".") if p.lower() not in _GENERICOS] or pacote.split(".")[-1:]
    return " ".join(p.replace("_", " ").capitalize() for p in partes)


def _consultar(pacote):
    endereco = f"https://play.google.com/store/apps/details?id={pacote}&hl=pt_BR"
    pedido = urllib.request.Request(endereco, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(pedido, timeout=8) as resposta:
            # o <title> fica depois de 1 MB de scripts, então precisa da página inteira
            pagina = resposta.read(4_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # 404 = app não está na loja (de fábrica ou instalado por fora); resposta definitiva
        return "" if e.code == 404 else None
    except (OSError, ValueError):
        return None  # sem internet: tenta de novo na próxima vez
    achado = _TITULO.search(pagina)
    if not achado:
        return None  # página mudou de formato: não guarda, para tentar de novo depois
    return _SUFIXO.sub("", html.unescape(achado.group(1)).strip())


def descobrir(pacotes):
    """Devolve {pacote: (nome, confirmado)}; confirmado=False quando é palpite."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}

    faltando = [p for p in pacotes if p not in cache]
    if faltando and CONSULTAR_PLAY_STORE:
        with ThreadPoolExecutor(max_workers=8) as grupo:
            for pacote, nome in zip(faltando, grupo.map(_consultar, faltando)):
                if nome is not None:
                    cache[pacote] = nome
        try:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    return {p: (cache[p], True) if cache.get(p) else (nome_provavel(p), False) for p in pacotes}

"""Coleta de SMS, contatos, chamadas, apps e contas."""
import csv
import re
from collections import Counter
from datetime import datetime

from . import adb, nomes_apps
from .leitura import problema

_INICIO_LINHA = re.compile(r"^Row: \d+ ")
_CONTA = re.compile(r"Account \{name=(.+?), type=(.+?)\}")
_ATRIBUTO = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
_INICIO_PACOTE = re.compile(r"^  Package \[", re.MULTILINE)

TIPO_SMS = {"1": "Recebida", "2": "Enviada", "3": "Rascunho"}
TIPO_CHAMADA = {
    "1": "Recebida",
    "2": "Efetuada",
    "3": "Perdida",
    "4": "Correio de voz",
    "5": "Rejeitada",
    "6": "Bloqueada",
}
# app de fábrica só entra na lista se foi usado pelo menos isto
_USO_MINIMO = 60


def interpretar(saida, colunas):
    """Transforma a saída do `content query` em lista de dicionários.

    A última coluna pode ter vírgulas e quebras de linha (texto livre).
    """
    blocos, atual = [], None
    for linha in saida.split("\n"):
        if _INICIO_LINHA.match(linha):
            if atual is not None:
                blocos.append(atual)
            atual = _INICIO_LINHA.sub("", linha, count=1)
        elif atual is not None:
            atual += "\n" + linha
    if atual is not None:
        blocos.append(atual)

    registros = []
    for bloco in blocos:
        registro = _separar(bloco.rstrip("\n"), colunas)
        if registro is not None:
            registros.append(registro)
    return registros


def _separar(texto, colunas):
    valores, pos = {}, 0
    for i, coluna in enumerate(colunas):
        prefixo = f"{coluna}="
        if not texto.startswith(prefixo, pos):
            return None
        inicio = pos + len(prefixo)
        if i + 1 < len(colunas):
            fim = texto.find(f", {colunas[i + 1]}=", inicio)
            if fim < 0:
                return None
            pos = fim + 2
        else:
            fim = len(texto)
        valor = texto[inicio:fim]
        valores[coluna] = "" if valor == "NULL" else valor
    return valores


def consultar(serial, uri, colunas):
    """Lê uma tabela do Android. Recusa e erro viram exceção com o motivo, nunca lista vazia."""
    resposta = adb.consultar(
        f"content query --uri {uri} --projection {':'.join(colunas)}",
        serial,
        timeout=600,
    )
    ruim = problema(resposta)
    if ruim:
        raise adb.AdbErro(f"{ruim[0]}: {ruim[1]}")
    registros = interpretar(resposta.saida, colunas)
    if not registros and "No result found" not in resposta.saida:
        motivo = resposta.saida.strip().splitlines()[0][:200] if resposta.saida.strip() else "resposta vazia"
        raise adb.AdbErro(f"resposta inesperada do aparelho: {motivo}")
    return registros


def data_hora(milissegundos):
    try:
        return datetime.fromtimestamp(int(milissegundos) / 1000).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def duracao(segundos):
    try:
        segundos = int(segundos)
    except (TypeError, ValueError):
        return ""
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min"
    return f"{minutos}min {segundos:02d}s" if minutos else f"{segundos}s"


def eh_pessoa(remetente):
    """Falso para operadora e serviços: nome em letras (VIVO, TIM) ou número curto."""
    if re.search(r"[A-Za-z]", remetente or ""):
        return False
    return len(re.sub(r"\D", "", remetente or "")) >= 8


def chave_numero(numero):
    """Últimos 8 dígitos: junta +55 42 9 9999-0001 e 99990001 na mesma conversa."""
    digitos = re.sub(r"\D", "", numero or "")
    return digitos[-8:] if len(digitos) >= 8 else digitos


def salvar_csv(caminho, cabecalho, linhas):
    # utf-8-sig + ponto e vírgula para abrir direto no Excel em português
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def contatos(serial, pasta=None):
    """Devolve [(nome, numero)]. Com `pasta`, grava também o contatos.csv."""
    registros = consultar(
        serial, "content://com.android.contacts/data/phones", ["data1", "display_name"]
    )
    linhas = sorted({(r["display_name"], r["data1"]) for r in registros})
    if pasta:
        salvar_csv(pasta / "contatos.csv", ["Nome", "Numero"], linhas)
    return linhas


def sms(serial, pasta, agenda=()):
    """Salva as conversas com pessoas em sms.csv e sms.txt.

    Devolve (conversas, excluidas). Cada conversa é um dicionário com numero, nome e
    mensagens [(data, tipo, texto)] em ordem de data. `excluidas` é {remetente: quantidade}
    do que o filtro deixou de fora; o texto dessas mensagens não é gravado.
    """
    registros = consultar(serial, "content://sms", ["address", "date", "type", "body"])
    pessoas = [r for r in registros if eh_pessoa(r["address"])]
    excluidas = Counter(r["address"] or "(sem remetente)" for r in registros if not eh_pessoa(r["address"]))
    salvar_csv(
        pasta / "sms_filtro.csv",
        ["Remetente excluido pelo filtro", "Motivo", "Mensagens"],
        [
            [remetente, "remetente com letras" if re.search(r"[A-Za-z]", remetente) else "menos de 8 dígitos", n]
            for remetente, n in excluidas.most_common()
        ],
    )
    nomes = {chave_numero(numero): nome for nome, numero in agenda if nome}

    grupos = {}
    for r in sorted(pessoas, key=lambda r: int(r["date"] or 0)):
        chave = chave_numero(r["address"])
        conversa = grupos.setdefault(
            chave, {"numero": r["address"], "nome": nomes.get(chave, ""), "mensagens": [], "ultima": 0}
        )
        conversa["mensagens"].append(
            (data_hora(r["date"]), TIPO_SMS.get(r["type"], r["type"]), r["body"])
        )
        conversa["ultima"] = int(r["date"] or 0)
    conversas = sorted(grupos.values(), key=lambda c: c["ultima"], reverse=True)

    salvar_csv(
        pasta / "sms.csv",
        ["Numero", "Nome", "Data", "Tipo", "Mensagem"],
        [
            [c["numero"], c["nome"], data, tipo, texto]
            for c in conversas
            for data, tipo, texto in c["mensagens"]
        ],
    )
    (pasta / "sms.txt").write_text(conversas_em_texto(conversas), encoding="utf-8-sig")
    return conversas, dict(excluidas)


def titulo_da_conversa(conversa):
    quem = f"{conversa['nome']} ({conversa['numero']})" if conversa["nome"] else conversa["numero"]
    return f"Conversa com {quem} - {len(conversa['mensagens'])} mensagens"


def conversas_em_texto(conversas):
    linhas = ["CONVERSAS POR SMS", f"{len(conversas)} conversas com pessoas", ""]
    for conversa in conversas:
        linhas += ["=" * 70, titulo_da_conversa(conversa), "=" * 70]
        for data, tipo, texto in conversa["mensagens"]:
            linhas.append(f"[{data}] {tipo}: {texto}")
        linhas.append("")
    return "\r\n".join(linhas)


def chamadas(serial, pasta):
    """Devolve [(numero, nome, data, duração, tipo)], da mais recente para a mais antiga."""
    registros = consultar(
        serial, "content://call_log/calls", ["number", "date", "duration", "type", "name"]
    )
    registros.sort(key=lambda r: int(r["date"] or 0), reverse=True)
    linhas = [
        (
            r["number"],
            r["name"],
            data_hora(r["date"]),
            duracao(r["duration"]),
            TIPO_CHAMADA.get(r["type"], r["type"]),
        )
        for r in registros
    ]
    salvar_csv(pasta / "chamadas.csv", ["Numero", "Nome", "Data", "Duracao", "Tipo"], linhas)
    return linhas


def interpretar_pacotes(saida):
    """Lê o `dumpsys package packages`: {pacote: {versao, instalado, atualizado}}."""
    pacotes = {}
    for bloco in _INICIO_PACOTE.split(saida)[1:]:
        nome = bloco.split("]", 1)[0]

        def campo(chave, padrao=r"(\S+)"):
            achado = re.search(rf"\b{chave}={padrao}", bloco)
            return achado.group(1) if achado else ""

        pacotes.setdefault(
            nome,
            {
                "versao": campo("versionName"),
                "instalado": _data_iso(campo("firstInstallTime", r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")),
                "atualizado": _data_iso(campo("lastUpdateTime", r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")),
            },
        )
    return pacotes


def interpretar_uso(saida):
    """Lê o `dumpsys usagestats`: {pacote: {segundos, ultimo}} com o maior valor registrado."""
    uso = {}
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha.startswith("package="):
            continue
        atributos = {chave: a or b for chave, a, b in _ATRIBUTO.findall(linha)}
        pacote = atributos.get("package", "")
        segundos = _segundos(atributos.get("totalTimeUsed") or atributos.get("totalTime") or "")
        ultimo = atributos.get("lastTimeUsed") or atributos.get("lastTime") or ""
        if not re.match(r"(19[89]\d|20\d\d)-", ultimo) or ultimo.startswith("1970"):
            ultimo = ""
        atual = uso.setdefault(pacote, {"segundos": 0, "ultimo": ""})
        atual["segundos"] = max(atual["segundos"], segundos)
        atual["ultimo"] = max(atual["ultimo"], ultimo[:19])
    return uso


def _segundos(texto):
    """Aceita "1:02:03", "02:03", "02:03.450" e milissegundos puros."""
    texto = texto.strip()
    if texto.isdigit():
        return int(texto) // 1000
    try:
        partes = [float(p) for p in texto.split(":")]
    except ValueError:
        return 0
    total = 0
    for parte in partes:
        total = total * 60 + parte
    return int(total)


def _data_iso(texto):
    """2026-09-29 10:00:00 -> 29/09/2026 10:00"""
    try:
        return datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return ""


def apps(serial, pasta):
    """Apps instalados pelo usuário e apps de fábrica que foram usados.

    Devolve lista de dicionários, do usado mais recentemente para o nunca usado.
    """
    saida = adb.shell("pm list packages -3", serial, timeout=120)
    do_usuario = {
        linha.split(":", 1)[1].strip() for linha in saida.splitlines() if linha.startswith("package:")
    }
    detalhes = interpretar_pacotes(adb.shell("dumpsys package packages", serial, timeout=300))
    bruto = adb.shell("dumpsys usagestats", serial, timeout=300)
    (pasta / "uso_apps_bruto.txt").write_text(bruto, encoding="utf-8")
    uso = interpretar_uso(bruto)

    usados = {p for p, u in uso.items() if u["segundos"] >= _USO_MINIMO and p in detalhes}
    nomes = nomes_apps.descobrir(sorted(do_usuario | usados))

    lista = []
    for pacote, (nome, confirmado) in nomes.items():
        info, u = detalhes.get(pacote, {}), uso.get(pacote, {"segundos": 0, "ultimo": ""})
        lista.append(
            {
                "nome": nome if confirmado else f"{nome} (nome provável)",
                "pacote": pacote,
                "origem": "Instalado pelo usuário" if pacote in do_usuario else "De fábrica",
                "versao": info.get("versao", ""),
                "instalado": info.get("instalado", ""),
                "atualizado": info.get("atualizado", ""),
                "ultimo_uso": _data_iso(u["ultimo"]),
                "tempo_de_uso": duracao(u["segundos"]) if u["segundos"] else "",
                "_ordem": (u["ultimo"], u["segundos"]),
            }
        )
    lista.sort(key=lambda a: a["_ordem"], reverse=True)

    salvar_csv(
        pasta / "apps.csv",
        ["Nome", "Pacote", "Origem", "Versao", "Instalado em", "Atualizado em", "Ultimo uso", "Tempo de uso"],
        [
            [a["nome"], a["pacote"], a["origem"], a["versao"], a["instalado"], a["atualizado"],
             a["ultimo_uso"], a["tempo_de_uso"]]
            for a in lista
        ],
    )
    return lista


def listar_contas(serial):
    """Contas logadas no aparelho (só o identificador, senha não é acessível)."""
    saida = adb.shell("dumpsys account", serial, timeout=120)
    return sorted(set(_CONTA.findall(saida)))


def contas(serial, pasta):
    encontradas = listar_contas(serial)
    salvar_csv(pasta / "contas.csv", ["Conta", "Tipo"], encontradas)
    return encontradas

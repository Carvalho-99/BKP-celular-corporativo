"""Identificação de um aparelho Android pelo cabo.

Cada informação vira uma Leitura com situação, método e motivo. O que é lido
do aparelho fica separado do que é sugestão (nome do funcionário) e do que o
técnico confirma na tela.
"""
import html
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from . import adb, coleta
from .leitura import (
    COLETADO, FALHA, GRUPO_APARELHO, GRUPO_CHIPS, GRUPO_USUARIO, NAO_ENCONTRADO, NAO_SUPORTADO,
    NEGADO, Registro, problema, resumir,
)

_ENTRE_ASPAS = re.compile(r"'([^']*)'")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PROPRIEDADE = re.compile(r"^\[(.+?)\]: \[(.*)\]$")
# uma assinatura por linha; não dá para parar no primeiro "]" porque os valores ocultos vêm como [****]
_CHIP = re.compile(r"\[SubscriptionInfoInternal: (.*)")
_ROTULO_LINHA = re.compile(r"^(n[úu]mero d[eo] (telefone|celular)|phone number|meu n[úu]mero)\b", re.I)
_CODIGOS_TELEFONIA = range(1, 31)
_ARGUMENTOS_TELEFONIA = (
    "s16 com.android.shell",
    "i32 0 s16 com.android.shell",
    "i32 1 s16 com.android.shell",
)
_CODIGO_BRASIL_CHIP = "724"  # começo do IMSI (identidade do chip), que também tem 15 dígitos
_TELEFONIA = "serviço de telefonia do Android (iphonesubinfo)"

# e-mail fora destes provedores é tratado como conta da empresa
PROVEDORES_PESSOAIS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com",
    "outlook.com.br", "live.com", "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com",
    "me.com", "bol.com.br", "uol.com.br", "terra.com.br",
}

TIPOS_DE_CONTA = {
    "com.google": "Google",
    "com.google.android.apps.tachyon": "Google Meet",
    "com.osp.app.signin": "Samsung account",
    "com.samsung.android.coreapps": "Samsung (perfil de contato)",
    "com.samsung.android.mobileservice": "Samsung (serviços)",
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "com.microsoft.workaccount": "Microsoft (conta de trabalho)",
    "com.microsoft.skydrive": "OneDrive",
    "com.microsoft.office.outlook.USER_ACCOUNT": "Outlook",
    "com.microsoft.teams": "Teams",
    "com.google.android.gm.exchange": "Exchange",
    "com.google.android.gm.legacyimap": "E-mail IMAP",
    "org.telegram.messenger": "Telegram",
    "com.facebook.auth.login": "Facebook",
    "com.facebook.messenger": "Messenger",
    "com.instagram.android": "Instagram",
    "com.linkedin.android": "LinkedIn",
}

_ESTADO_BATERIA = {"1": "estado desconhecido", "2": "carregando", "3": "descarregando",
                   "4": "sem carregar", "5": "carga completa"}
_SAUDE_BATERIA = {"2": "saúde boa", "3": "superaquecida", "4": "esgotada", "5": "sobretensão",
                  "6": "falha", "7": "fria"}


@dataclass
class Candidato:
    nome: str
    fontes: list


@dataclass
class Sugestao:
    valor: str
    fonte: str


@dataclass
class Identificacao:
    plataforma: str
    serial: str
    titulo: str
    leituras: list = field(default_factory=list)
    candidatos: list = field(default_factory=list)  # nomes sugeridos, já sem repetição
    campos: dict = field(default_factory=dict)  # campo do formulário -> Sugestao
    quando: datetime = field(default_factory=datetime.now)
    registro_em: object = None

    @property
    def conflito(self):
        return len(self.candidatos) > 1

    def coletadas(self):
        return [l for l in self.leituras if l.coletada]

    def nao_obtidas(self):
        return [l for l in self.leituras if not l.coletada]


# ---------- funções de formato, sem aparelho ----------

def luhn_valido(digitos):
    """Dígito verificador do IMEI. Confere o formato; não prova de onde o número veio."""
    soma = 0
    for i, caractere in enumerate(reversed(digitos)):
        n = int(caractere)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        soma += n
    return soma % 10 == 0


def eh_imei(digitos):
    return (
        len(digitos) == 15 and digitos.isdigit() and luhn_valido(digitos)
        and not digitos.startswith(_CODIGO_BRASIL_CHIP)
    )


def texto_do_parcel(saida):
    """Extrai o texto da resposta do `service call` (vem em blocos com pontos no meio)."""
    return "".join(_ENTRE_ASPAS.findall(saida)).replace(".", "")


def eh_linha(texto):
    """Número brasileiro com DDD: 10 ou 11 dígitos, com ou sem o 55 na frente."""
    digitos = re.sub(r"\D", "", texto or "")
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    digitos = digitos.lstrip("0") if len(digitos) == 12 else digitos
    return len(digitos) in (10, 11) and digitos[0] != "0" and digitos[2] in "23456789"


def numero_na_tela(tela):
    """Número que aparece logo depois do rótulo "Número de telefone". Sem rótulo, não aceita."""
    textos = [html.unescape(t).strip() for t in re.findall(r'\btext="([^"]*)"', tela)]
    textos = [t for t in textos if t]
    for i, texto in enumerate(textos[:-1]):
        if _ROTULO_LINHA.search(texto) and eh_linha(textos[i + 1]):
            return textos[i + 1]
    return ""


def nome_pelo_email(email):
    """joao.silva@empresa.com -> "Joao Silva". Só arrisca se tiver nome e sobrenome."""
    partes = [p for p in re.split(r"[._\-\d]+", email.split("@")[0]) if p.isalpha()]
    return " ".join(p.capitalize() for p in partes) if len(partes) >= 2 else ""


def nome_pelo_aparelho(nome):
    """"A16 de Bruno" -> "Bruno"; "Bruno's Galaxy" -> "Bruno"."""
    achado = re.search(r"\bde (.+)$", nome or "", re.IGNORECASE) or re.match(r"(.+?)['’]s\b", nome or "")
    return achado.group(1).strip() if achado else ""


def _palavras(nome):
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return {p for p in re.split(r"\W+", sem_acento.lower()) if p}


def juntar_candidatos(pares):
    """Recebe [(nome, fonte)] e devolve os nomes distintos.

    "Bruno" e "Bruno Carvalho" contam como a mesma pessoa. Fica o nome da fonte que veio
    primeiro na lista (a mais confiável), a não ser que ele seja uma palavra só.
    "Bruno Carvalho" e "Maria Souza" ficam como dois candidatos, para o técnico escolher.
    """
    candidatos = []
    for nome, fonte in pares:
        nome = (nome or "").strip()
        if not nome:
            continue
        for candidato in candidatos:
            a, b = _palavras(nome), _palavras(candidato.nome)
            if a <= b or b <= a:
                if len(b) == 1 and len(a) > 1:
                    candidato.nome = nome
                candidato.fontes.append(fonte)
                break
        else:
            candidatos.append(Candidato(nome, [fonte]))
    return candidatos


def separar_contas(contas):
    """Das contas do AccountManager tira e-mails e o que cada provedor registrou.

    Devolve (corporativos, pessoais, {provedor: [identificadores]}).
    Conta registrada não prova uso ativo: só mostra que existe um cadastro no aparelho.
    """
    corporativos, pessoais, provedores = [], [], {}
    for nome, tipo in contas:
        provedor = TIPOS_DE_CONTA.get(tipo, tipo)
        achado = _EMAIL.search(nome)
        identificador = achado.group().lower() if achado else ""
        lista = provedores.setdefault(provedor, [])
        if identificador and identificador not in lista:
            lista.append(identificador)
        if identificador:
            destino = pessoais if identificador.split("@")[1] in PROVEDORES_PESSOAIS else corporativos
            if identificador not in destino:
                destino.append(identificador)
    return corporativos, pessoais, provedores


def ler_chips(saida_isub):
    """Chips ativos segundo o `dumpsys isub`: [{compartimento, operadora, embutido, inicio_da_linha}]."""
    chips = {}
    for bloco in _CHIP.findall(saida_isub):
        campos = dict(re.findall(r"(\w+)=(\S*)", bloco))
        indice = campos.get("simSlotIndex", "")
        if not campos.get("id") or not indice.lstrip("-").isdigit():
            continue
        compartimento = int(indice)
        if compartimento < 0:
            continue  # chip que já passou pelo aparelho, mas não está nele agora
        numero = campos.get("number", "")
        chips[campos["id"]] = {
            "compartimento": compartimento + 1,
            "operadora": campos.get("carrierName") or campos.get("displayName") or "",
            "embutido": campos.get("isEmbedded") == "1",
            "numero": numero if "[" not in numero else "",
            "inicio_da_linha": numero.split("[")[0] if "[" in numero else "",
            "pais_operadora": f"{campos.get('mcc', '')}-{campos.get('mnc', '')}".strip("-"),
        }
    return sorted(chips.values(), key=lambda c: c["compartimento"])


# ---------- leitura do aparelho ----------

def identificar(serial, ler_tela=True):
    """Lê tudo que o Android entrega sobre o aparelho, os chips e o usuário."""
    registro = Registro(f"Android {serial}")

    def etapa(grupo, item, padrao, funcao, *argumentos):
        """Erro inesperado em uma leitura vira Falha com motivo, sem derrubar as outras."""
        try:
            return funcao(serial, *argumentos, registro)
        except Exception as e:  # noqa: BLE001 - qualquer erro precisa aparecer no registro
            registro.anotar(
                grupo, item, FALHA, metodo=funcao.__name__.strip("_"),
                motivo=f"erro ao interpretar a resposta do aparelho ({type(e).__name__}: {e})",
            )
            return padrao

    propriedades = etapa(GRUPO_APARELHO, "Propriedades do sistema", {}, _propriedades)
    etapa(GRUPO_APARELHO, "Dados do aparelho", None, _aparelho, propriedades)
    etapa(GRUPO_APARELHO, "Armazenamento", None, _armazenamento)
    etapa(GRUPO_APARELHO, "Bateria", None, _bateria)

    telefonia = etapa(GRUPO_APARELHO, "IMEI", "o serviço de telefonia não pôde ser lido", _varrer_telefonia)
    imeis = etapa(GRUPO_APARELHO, "IMEI", [], _imeis, telefonia)
    chips = etapa(GRUPO_CHIPS, "Chips no aparelho", [], _chips, propriedades)
    linhas = etapa(GRUPO_CHIPS, "Número da linha", [], _linhas, telefonia, chips, ler_tela)

    nome_aparelho = etapa(GRUPO_USUARIO, "Nome dado ao aparelho", "", _nome_do_aparelho)
    perfil = etapa(GRUPO_USUARIO, "Nome no perfil do aparelho", "", _perfil)
    etapa(GRUPO_USUARIO, "Nome do usuário local", None, _usuario_local)
    corporativos, pessoais, provedores = etapa(GRUPO_USUARIO, "Contas do aparelho", ([], [], {}), _contas)

    candidatos = juntar_candidatos(
        [(perfil, "nome no perfil do aparelho")]
        + [(nome_pelo_email(e), f"e-mail corporativo {e}") for e in corporativos]
        + [(nome_pelo_email(e), f"e-mail pessoal {e}") for e in pessoais]
        + [(nome_pelo_aparelho(nome_aparelho), f"nome dado ao aparelho (“{nome_aparelho}”)")]
    )

    campos = {}
    if len(candidatos) == 1:
        campos["funcionario"] = Sugestao(candidatos[0].nome, "sugerido por " + "; ".join(candidatos[0].fontes))
    if imeis:
        campos["imei"] = Sugestao(" / ".join(imeis), _TELEFONIA)
    if linhas:
        campos["linha"] = Sugestao(" / ".join(n for n, _ in linhas), linhas[0][1])
    google = provedores.get("Google", [])
    if len(google) == 1:
        campos["conta_whatsapp"] = Sugestao(
            google[0], "única conta Google do aparelho; confirme na tela de backup do WhatsApp"
        )

    titulo = " ".join(
        p for p in (propriedades.get("ro.product.manufacturer", "").title(), propriedades.get("ro.product.model", "")) if p
    )
    resultado = Identificacao("Android", serial, titulo or "Aparelho Android", registro.leituras, candidatos, campos)
    resultado.registro_em = registro.gravar()
    return resultado


def _consultar(serial, comando, registro, grupo, item, metodo, timeout=60):
    """Roda o comando; se não houve resposta útil já anota o motivo e devolve None."""
    try:
        resposta = adb.consultar(comando, serial, timeout)
    except adb.AdbErro as e:
        registro.anotar(grupo, item, FALHA, metodo=metodo, motivo=f"sem comunicação com o aparelho: {e}")
        return None
    ruim = problema(resposta)
    if ruim:
        registro.anotar(grupo, item, ruim[0], metodo=metodo, motivo=ruim[1])
        return None
    return resposta


def _propriedades(serial, registro):
    resposta = _consultar(serial, "getprop", registro, GRUPO_APARELHO, "Propriedades do sistema", "getprop")
    propriedades = {}
    for linha in (resposta.saida if resposta else "").splitlines():
        achado = _PROPRIEDADE.match(linha.strip())
        if achado:
            propriedades[achado.group(1)] = achado.group(2)
    return propriedades


def _aparelho(serial, p, registro):
    registro.coletado(
        GRUPO_APARELHO, "Identificador da conexão USB (ADB)", serial, "lista de aparelhos do ADB"
    )
    if not p:
        return  # as propriedades não foram lidas e o motivo já está anotado; não é "propriedade vazia"

    def anotar(item, valor, chave):
        metodo = f"propriedade do sistema ({chave})"
        if valor:
            registro.coletado(GRUPO_APARELHO, item, valor, metodo)
        else:
            registro.anotar(GRUPO_APARELHO, item, NAO_ENCONTRADO, metodo=metodo, motivo="propriedade vazia")

    anotar("Fabricante", p.get("ro.product.manufacturer", "").title(), "ro.product.manufacturer")
    anotar("Modelo", p.get("ro.product.model", ""), "ro.product.model")
    versao = p.get("ro.build.version.release", "")
    if versao and p.get("ro.build.version.sdk"):
        versao += f" (API {p['ro.build.version.sdk']})"
    anotar("Versão do Android", versao, "ro.build.version.release")
    anotar("Atualização de segurança", p.get("ro.build.version.security_patch", ""), "ro.build.version.security_patch")
    anotar("Compilação", p.get("ro.build.display.id", ""), "ro.build.display.id")
    anotar("Número de série", p.get("ro.serialno") or p.get("ro.boot.serialno", ""), "ro.serialno")


def _armazenamento(serial, registro):
    metodo = "espaço em disco (df /data)"
    resposta = _consultar(serial, "df -k /data", registro, GRUPO_APARELHO, "Armazenamento", metodo)
    if not resposta:
        return
    for linha in resposta.saida.splitlines()[1:]:
        partes = linha.split()
        if len(partes) >= 4 and partes[1].isdigit() and partes[3].isdigit():
            total, livre = int(partes[1]) / 1024 ** 2, int(partes[3]) / 1024 ** 2
            registro.coletado(
                GRUPO_APARELHO, "Armazenamento", f"{total:.1f} GB no total, {livre:.1f} GB livres", metodo
            )
            return
    registro.anotar(GRUPO_APARELHO, "Armazenamento", FALHA, metodo=metodo, motivo="resposta em formato inesperado")


def _bateria(serial, registro):
    metodo = "serviço de bateria (dumpsys battery)"
    resposta = _consultar(serial, "dumpsys battery", registro, GRUPO_APARELHO, "Bateria", metodo)
    if not resposta:
        return
    campos = dict(re.findall(r"^\s*(level|scale|status|health|temperature): (\S+)", resposta.saida, re.M))
    if not campos.get("level", "").isdigit():
        registro.anotar(GRUPO_APARELHO, "Bateria", FALHA, metodo=metodo, motivo="resposta em formato inesperado")
        return
    partes = [f"{int(campos['level']) * 100 // int(campos.get('scale') or 100)}%"]
    partes.append(_ESTADO_BATERIA.get(campos.get("status"), ""))
    partes.append(_SAUDE_BATERIA.get(campos.get("health"), ""))
    if campos.get("temperature", "").lstrip("-").isdigit():
        partes.append(f"{int(campos['temperature']) / 10:.1f} °C".replace(".", ","))
    registro.coletado(GRUPO_APARELHO, "Bateria", ", ".join(p for p in partes if p), metodo)


def _varrer_telefonia(serial, registro):
    """Pergunta ao serviço de telefonia tudo que ele responde: [(código, argumentos, texto)].

    O código de cada informação muda conforme a versão do Android, então em vez de
    adivinhar, lê todos e separa pelo formato, guardando de qual código veio.
    """
    codigos = " ".join(str(c) for c in _CODIGOS_TELEFONIA)
    variantes = " ".join(f'"{a}"' for a in _ARGUMENTOS_TELEFONIA)
    comando = (
        f'for c in {codigos}; do for a in {variantes}; do echo "@@$c|$a"; '
        "service call iphonesubinfo $c $a; done; done"
    )
    try:
        resposta = adb.consultar(comando, serial, timeout=120)
    except adb.AdbErro as e:
        return f"sem comunicação com o aparelho: {e}"
    respostas = []
    for bloco in resposta.saida.split("@@")[1:]:
        cabecalho, _, corpo = bloco.partition("\n")
        codigo, _, argumentos = cabecalho.partition("|")
        texto = texto_do_parcel(corpo).strip()
        if texto:
            respostas.append((codigo.strip(), argumentos.strip(), texto))
    if not respostas:
        return resumir(resposta.tudo) or "o serviço de telefonia não respondeu"
    return respostas


def _imeis(serial, telefonia, registro):
    if isinstance(telefonia, str):
        registro.anotar(GRUPO_APARELHO, "IMEI", FALHA, metodo=_TELEFONIA, motivo=telefonia)
        return []
    encontrados = {}
    for codigo, argumentos, texto in telefonia:
        for digitos in re.findall(r"(?<!\d)\d{15}(?!\d)", texto):
            if eh_imei(digitos):
                encontrados.setdefault(digitos, f"{_TELEFONIA}, código {codigo}")
    for ordem, (numero, metodo) in enumerate(list(encontrados.items())[:2], start=1):
        registro.coletado(
            GRUPO_APARELHO, f"IMEI {ordem}", numero, metodo + "; formato conferido pelo dígito verificador"
        )
    if encontrados:
        return list(encontrados)[:2]

    # plano B: comando direto, que em muitos aparelhos exige permissão de sistema
    recusas = [t for _, _, t in telefonia if re.search(r"requirement|permission|not allowed", t, re.I)]
    ruim = None
    for compartimento in (0, 1):
        try:
            resposta = adb.consultar(f"cmd phone get-imei {compartimento}", serial)
        except adb.AdbErro as e:
            registro.anotar(GRUPO_APARELHO, "IMEI", FALHA, metodo="cmd phone get-imei", motivo=str(e))
            return []
        achado = re.search(r"(?<!\d)\d{15}(?!\d)", resposta.saida)
        if achado and eh_imei(achado.group()):
            encontrados[achado.group()] = f"comando cmd phone get-imei {compartimento}"
            registro.coletado(
                GRUPO_APARELHO, f"IMEI {len(encontrados)}", achado.group(), encontrados[achado.group()]
            )
        elif compartimento == 0 and not encontrados:
            ruim = problema(resposta)
    if not encontrados:
        situacao = NEGADO if recusas or (ruim and ruim[0] == NEGADO) else NAO_ENCONTRADO
        motivo = (
            "o Android recusou a leitura do IMEI pelo cabo neste aparelho; disque *#06# e digite"
            if situacao == NEGADO else "nenhuma resposta tinha formato de IMEI; disque *#06# e digite"
        )
        registro.anotar(
            GRUPO_APARELHO, "IMEI", situacao, metodo=f"{_TELEFONIA} e cmd phone get-imei", motivo=motivo
        )
    return list(encontrados)[:2]


def _chips(serial, propriedades, registro):
    metodo = "serviço de assinaturas (dumpsys isub)"
    resposta = _consultar(serial, "dumpsys isub", registro, GRUPO_CHIPS, "Chips no aparelho", metodo)
    chips = ler_chips(resposta.saida) if resposta else []
    if resposta and not chips:
        estados = propriedades.get("gsm.sim.state", "")
        registro.anotar(
            GRUPO_CHIPS, "Chips no aparelho", NAO_ENCONTRADO, metodo=metodo,
            motivo=f"nenhum chip ativo (estado informado: {estados or 'vazio'})",
        )
    for chip in chips:
        partes = [chip["operadora"] or "operadora não informada", "eSIM" if chip["embutido"] else "chip físico"]
        if chip["numero"]:
            partes.append(f"linha {chip['numero']}")
        elif chip["inicio_da_linha"]:
            partes.append(f"linha começa com {chip['inicio_da_linha']} (o Android oculta o resto nesta consulta)")
        else:
            partes.append("o chip não guarda o próprio número")
        registro.coletado(GRUPO_CHIPS, f"Chip do compartimento {chip['compartimento']}", ", ".join(partes), metodo)

    operadoras = [o.strip() for o in propriedades.get("gsm.sim.operator.alpha", "").split(",") if o.strip()]
    if operadoras:
        registro.coletado(
            GRUPO_CHIPS, "Operadora", " / ".join(dict.fromkeys(o.upper() for o in operadoras)),
            "propriedade do sistema (gsm.sim.operator.alpha)",
        )
    return chips


def _linhas(serial, telefonia, chips, ler_tela, registro):
    """Tenta do jeito mais discreto para o mais visível. Devolve [(número, método)]."""
    tentativas = []

    try:
        resposta = adb.consultar(
            "content query --uri content://telephony/siminfo --projection number", serial
        )
        ruim = problema(resposta)
        if ruim:
            tentativas.append(f"tabela de chips: {ruim[0].lower()}")
        else:
            numeros = [r["number"] for r in coleta.interpretar(resposta.saida, ["number"]) if eh_linha(r["number"])]
            if numeros:
                return _anotar_linhas(numeros, "tabela de chips do Android (siminfo)", chips, registro, tentativas)
            tentativas.append("tabela de chips: sem número")
    except adb.AdbErro as e:
        tentativas.append(f"tabela de chips: sem comunicação ({e})")

    completos = [c["numero"] for c in chips if eh_linha(c["numero"])]
    if completos:
        return _anotar_linhas(completos, "serviço de assinaturas (dumpsys isub)", chips, registro, tentativas)
    if any(c["inicio_da_linha"] for c in chips):
        tentativas.append("serviço de assinaturas: número oculto pelo Android")
    elif chips:
        tentativas.append("serviço de assinaturas: sem número")
    else:
        lido = any(l.item.startswith("Chip") and l.situacao != FALHA for l in registro.leituras)
        tentativas.append(
            "serviço de assinaturas: nenhum chip ativo" if lido else "serviço de assinaturas: sem comunicação"
        )

    if isinstance(telefonia, str):
        tentativas.append(f"serviço de telefonia: {telefonia}")
    else:
        achados = {}
        for codigo, _, texto in telefonia:
            # 15 dígitos ou mais é IMEI, identidade ou série do chip, nunca a linha
            achado = re.search(r"(?<!\d)\+?\d{10,13}(?!\d)", texto)
            if achado and eh_linha(achado.group()):
                achados.setdefault(achado.group(), f"{_TELEFONIA}, código {codigo}")
        if achados:
            metodo = next(iter(achados.values()))
            return _anotar_linhas(list(achados), metodo, chips, registro, tentativas)
        tentativas.append("serviço de telefonia: sem número")

    if ler_tela:
        numero, motivo = _linha_pela_tela(serial)
        if numero:
            return _anotar_linhas(
                [numero], "tela Configurações > Sobre o telefone, campo “Número de telefone”",
                chips, registro, tentativas,
            )
        tentativas.append(f"tela Sobre o telefone: {motivo}")

    # se nenhuma fonte chegou a responder, o problema é a conexão, não a falta do número
    sem_resposta = all("sem comunicação" in t or "not found" in t or "offline" in t for t in tentativas)
    registro.anotar(
        GRUPO_CHIPS, "Número da linha", FALHA if sem_resposta else NAO_ENCONTRADO,
        metodo=f"{len(tentativas)} fontes consultadas",
        motivo="; ".join(tentativas) + ". Digite o número à mão",
    )
    return []


def _anotar_linhas(numeros, metodo, chips, registro, tentativas):
    if tentativas:  # as fontes que não responderam ficam registradas junto
        metodo += ". Fontes consultadas antes, sem resultado: " + "; ".join(tentativas)
    resultado = []
    for numero in dict.fromkeys(numeros):
        chip = next((c for c in chips if c["inicio_da_linha"] and numero.startswith(c["inicio_da_linha"])), None)
        item = "Número da linha"
        if chip:
            item += f" (chip do compartimento {chip['compartimento']}, {chip['operadora']})"
        registro.coletado(GRUPO_CHIPS, item, numero, metodo)
        resultado.append((numero, metodo))
    return resultado


def tela_bloqueada(serial):
    saida = adb.consultar("dumpsys window", serial, timeout=30).saida
    return bool(re.search(r"isKeyguardShowing=true|mShowingLockscreen=true|mDreamingLockscreen=true", saida))


def _linha_pela_tela(serial):
    """Abre Configurações > Sobre o telefone e lê o campo do número. Devolve (número, motivo)."""
    arquivo = "/sdcard/.backup_celular_tela.xml"
    try:
        if tela_bloqueada(serial):
            return "", "a tela do celular está bloqueada"
        adb.consultar("am start -a android.settings.DEVICE_INFO_SETTINGS", serial)
        time.sleep(2)
        try:
            resposta = adb.consultar(
                f"uiautomator dump {arquivo} >/dev/null 2>&1; cat {arquivo}; rm -f {arquivo}",
                serial, timeout=40,
            )
        finally:
            adb.consultar("input keyevent KEYCODE_HOME", serial)
    except adb.AdbErro as e:
        return "", f"sem comunicação: {e}"
    if "<hierarchy" not in resposta.saida:
        return "", "o aparelho não permitiu ler a tela"
    numero = numero_na_tela(resposta.saida)
    if numero:
        return numero, ""
    tem_rotulo = any(
        _ROTULO_LINHA.search(html.unescape(t).strip()) for t in re.findall(r'\btext="([^"]*)"', resposta.saida)
    )
    return "", (
        "o campo “Número de telefone” existe, mas está sem número" if tem_rotulo
        else "o campo “Número de telefone” não apareceu nessa tela"
    )


def _nome_do_aparelho(serial, registro):
    for chave in ("global device_name", "secure bluetooth_name"):
        try:
            nome = adb.consultar(f"settings get {chave}", serial).saida.strip()
        except adb.AdbErro as e:
            registro.anotar(GRUPO_USUARIO, "Nome dado ao aparelho", FALHA, metodo="settings get", motivo=str(e))
            return ""
        if nome and nome != "null":
            registro.coletado(GRUPO_USUARIO, "Nome dado ao aparelho", nome, f"configuração do sistema ({chave})")
            return nome
    registro.anotar(
        GRUPO_USUARIO, "Nome dado ao aparelho", NAO_ENCONTRADO, metodo="configurações do sistema",
        motivo="o aparelho não tem nome definido",
    )
    return ""


def _perfil(serial, registro):
    item, metodo = "Nome no perfil do aparelho", "perfil “Eu” dos contatos"
    resposta = _consultar(
        serial, "content query --uri content://com.android.contacts/profile --projection display_name",
        registro, GRUPO_USUARIO, item, metodo,
    )
    if not resposta:
        return ""
    for linha in coleta.interpretar(resposta.saida, ["display_name"]):
        if linha["display_name"].strip():
            registro.coletado(GRUPO_USUARIO, item, linha["display_name"].strip(), metodo)
            return linha["display_name"].strip()
    registro.anotar(GRUPO_USUARIO, item, NAO_ENCONTRADO, metodo=metodo, motivo="o perfil não tem nome preenchido")
    return ""


def _usuario_local(serial, registro):
    item, metodo = "Nome do usuário local", "lista de usuários do Android (pm list users)"
    resposta = _consultar(serial, "pm list users", registro, GRUPO_USUARIO, item, metodo)
    if not resposta:
        return
    nomes = re.findall(r"UserInfo\{\d+:(.*?):[0-9a-f]+\}", resposta.saida)
    reais = [n for n in nomes if n and n.lower() not in ("null", "xxx", "owner", "proprietário")]
    if reais:
        registro.coletado(GRUPO_USUARIO, item, ", ".join(reais), metodo)
    else:
        registro.anotar(
            GRUPO_USUARIO, item, NAO_ENCONTRADO, metodo=metodo,
            motivo="o Android não informa o nome do usuário local pelo cabo nesta versão",
        )


def _contas(serial, registro):
    metodo = "contas registradas no Android (dumpsys account)"
    try:
        contas = coleta.listar_contas(serial)
    except adb.AdbErro as e:
        registro.anotar(GRUPO_USUARIO, "Contas do aparelho", FALHA, metodo=metodo, motivo=str(e))
        return [], [], {}
    if not contas:
        registro.anotar(
            GRUPO_USUARIO, "Contas do aparelho", NAO_ENCONTRADO, metodo=metodo,
            motivo="nenhuma conta registrada no aparelho",
        )
        return [], [], {}
    corporativos, pessoais, provedores = separar_contas(contas)
    if corporativos:
        registro.coletado(GRUPO_USUARIO, "E-mail corporativo", ", ".join(corporativos), metodo)
    else:
        registro.anotar(
            GRUPO_USUARIO, "E-mail corporativo", NAO_ENCONTRADO, metodo=metodo,
            motivo="nenhuma conta com domínio de empresa",
        )
    if pessoais:
        registro.coletado(GRUPO_USUARIO, "E-mails de provedor pessoal", ", ".join(pessoais), metodo)
    for provedor in sorted(provedores):
        identificadores = provedores[provedor]
        registro.coletado(
            GRUPO_USUARIO, f"Conta {provedor}",
            ", ".join(identificadores) if identificadores else "registrada, sem identificador visível",
            metodo,
        )
    return corporativos, pessoais, provedores


# ---------- usados pelo diagnostico.py ----------

def imei(serial):
    registro = Registro(serial)
    return " / ".join(_imeis(serial, _varrer_telefonia(serial, registro), registro))


def linha(serial):
    registro = Registro(serial)
    chips = _chips(serial, {}, registro)
    achadas = _linhas(serial, _varrer_telefonia(serial, registro), chips, True, registro)
    return " / ".join(numero for numero, _ in achadas)

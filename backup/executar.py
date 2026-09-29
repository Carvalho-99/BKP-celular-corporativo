"""Sequência completa do backup de um Android. A interface só chama rodar()."""
import csv
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import adb, arquivos, cobertura, coleta, device, relatorio, whatsapp
from .arquivos import Cancelado

OK = "OK"
PARCIAL = "Parcial"
FALHOU = "Falhou"
CANCELADO = "Cancelado"
NAO_EXECUTADA = "Não executada"

_SEM_CONEXAO = ("not found", "offline", "no devices", "unauthorized", "não respondeu", "closed")


@dataclass
class Dados:
    funcionario: str  # confirmado pelo técnico na tela
    tecnico: str
    setor: str = ""
    linha: str = ""
    imei: str = ""
    conta_whatsapp: str = ""
    observacoes: str = ""
    identificacao: object = None  # captura.Identificacao do aparelho, com leituras e sugestões


@dataclass
class Opcoes:
    arquivos: bool = True
    sms: bool = True
    contatos: bool = True
    chamadas: bool = True
    apps: bool = True
    whatsapp: bool = True


@dataclass
class Etapa:
    nome: str
    situacao: str
    detalhe: str = ""
    categoria: str = ""
    preservado: str = ""  # o que ficou guardado no backup
    legivel: str = ""  # o que dá para ler em planilha ou relatório
    inacessivel: str = ""  # o que não foi possível obter


@dataclass
class Resultado:
    pasta: Path
    etapas: list = field(default_factory=list)
    cancelado: bool = False

    @property
    def problemas(self):
        return [e for e in self.etapas if e.situacao != OK]

    def da_categoria(self, chave):
        return [e for e in self.etapas if e.categoria == chave]


class ConexaoPerdida(Exception):
    pass


class Tela:
    """O que rodar() precisa da interface. A janela implementa estes métodos."""

    def log(self, mensagem): ...

    def progresso(self, fracao, texto):
        """fracao de 0 a 1 é a parte dos bytes já copiada; None é etapa sem total conhecido."""

    def confirmar_whatsapp(self, apps):
        """Pede para o técnico fazer o backup no celular. Devolve False se ele pular."""
        return True

    def cancelado(self):
        return False


def nome_da_pasta(funcionario, momento):
    limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", funcionario).strip(". ") or "sem-nome"
    return f"{limpo} - {momento.strftime('%Y-%m-%d %Hh%M')}"


def sem_conexao(erro):
    texto = str(erro).lower()
    return isinstance(erro, adb.AdbErro) and any(marca in texto for marca in _SEM_CONEXAO)


def rodar(serial, dados, opcoes, raiz_destino, tela):
    aparelho = device.info(serial)
    inicio = datetime.now()
    pasta = Path(raiz_destino) / nome_da_pasta(dados.funcionario, inicio)
    pasta_dados = pasta / "dados"
    pasta_dados.mkdir(parents=True, exist_ok=False)

    registro = open(pasta / "log.txt", "w", encoding="utf-8")

    def log(mensagem):
        registro.write(f"{datetime.now():%H:%M:%S} {mensagem}\n")
        registro.flush()
        tela.log(mensagem)

    etapas, copias, contas, apps_whatsapp = [], [], [], []
    # conteúdo por extenso que vai para o detalhes.pdf
    detalhes = {"apps": [], "conversas": [], "chamadas": [], "contatos": []}
    limites = cobertura.CATEGORIAS  # só para os nomes
    pendentes = [chave for chave in limites if getattr(opcoes, chave)]

    def etapa(nome, categoria, funcao):
        """Roda uma coleta; se falhar, registra e segue para a próxima."""
        if tela.cancelado():
            raise Cancelado()
        log(f"{nome}...")
        tela.progresso(None, nome)
        try:
            feita = funcao()
            feita.nome, feita.categoria, feita.situacao = nome, categoria, feita.situacao or OK
            etapas.append(feita)
            log(f"  {feita.detalhe}")
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - o motivo vai para o relatório
            if sem_conexao(e):
                raise ConexaoPerdida(str(e)) from e
            etapas.append(Etapa(nome, FALHOU, str(e), categoria, inacessivel=f"tudo desta etapa: {e}"))
            log(f"  FALHOU: {e}")

    def concluida(chave):
        if chave in pendentes:
            pendentes.remove(chave)

    motivo_da_parada = ""
    cancelado = False
    try:
        log(f"Aparelho: {aparelho['fabricante']} {aparelho['modelo']} (Android {aparelho['android']})")

        if opcoes.whatsapp:
            apps_whatsapp = _etapa_whatsapp(serial, tela, log, etapas)
        if opcoes.contatos:
            etapa("Contatos", "contatos", lambda: _contatos(serial, pasta_dados, detalhes))
            concluida("contatos")
        if opcoes.sms:
            etapa("SMS", "sms", lambda: _sms(serial, pasta_dados, detalhes))
            concluida("sms")
        if opcoes.chamadas:
            etapa("Chamadas", "chamadas", lambda: _chamadas(serial, pasta_dados, detalhes))
            concluida("chamadas")
        if opcoes.apps:
            etapa("Apps e histórico de uso", "apps", lambda: _apps(serial, pasta_dados, detalhes))
            etapa("Contas do aparelho", "apps", lambda: _contas(serial, pasta_dados, contas))
            concluida("apps")

        pastas_whatsapp = [a.pasta for a in apps_whatsapp if a.pasta]
        if opcoes.arquivos or pastas_whatsapp:
            _etapa_arquivos(serial, opcoes, pastas_whatsapp, pasta, tela, log, etapas, copias)
        concluida("arquivos")
        if opcoes.whatsapp:
            _whatsapp_no_backup(pasta, apps_whatsapp, etapas)
            concluida("whatsapp")
    except Cancelado:
        cancelado = True
        motivo_da_parada = "cancelado pelo técnico"
        etapas.append(Etapa("Backup", CANCELADO, "Interrompido pelo técnico; backup incompleto"))
        log("Backup CANCELADO pelo técnico.")
    except ConexaoPerdida as e:
        motivo_da_parada = "conexão com o aparelho interrompida"
        etapas.append(Etapa("Backup", FALHOU, f"Conexão com o aparelho interrompida ({e})"))
        log(f"ERRO: conexão com o aparelho interrompida ({e})")
    except Exception as e:  # noqa: BLE001
        # erro inesperado: ainda assim gera o relatório do que foi feito
        motivo_da_parada = "conexão com o aparelho interrompida" if sem_conexao(e) else f"erro: {e}"
        etapas.append(Etapa("Backup", FALHOU, f"Interrompido: {motivo_da_parada}"))
        log(f"ERRO: {e}")

    if motivo_da_parada:
        if opcoes.whatsapp and "whatsapp" in pendentes:
            _whatsapp_no_backup(pasta, apps_whatsapp, etapas)
        for chave in pendentes:
            if chave == "whatsapp" and apps_whatsapp:
                continue  # já tem linha própria, preenchida com o que chegou a ser copiado
            if chave == "arquivos" and any(e.categoria == "arquivos" for e in etapas):
                continue
            etapas.append(
                Etapa(limites[chave], NAO_EXECUTADA, f"Não chegou a rodar: {motivo_da_parada}", chave,
                      inacessivel="nada desta categoria foi copiado")
            )
            log(f"  {limites[chave]}: NÃO EXECUTADA ({motivo_da_parada})")

    resultado = Resultado(pasta, etapas, cancelado)
    try:
        tela.progresso(None, "Gerando o relatório")
        resumo = {
            "dados": dados,
            "aparelho": aparelho,
            "inicio": inicio,
            "fim": datetime.now(),
            "etapas": etapas,
            "copias": copias,
            "contas": contas,
            "whatsapp": apps_whatsapp,
            "pasta": pasta,
            "detalhes": detalhes,
            "completo": not resultado.problemas,
        }
        relatorio.gerar(pasta / "relatorio.pdf", resumo)
        log(f"Relatório gerado: {pasta / 'relatorio.pdf'}")
        if any(detalhes.values()):
            tela.progresso(None, "Gerando o PDF com os dados por extenso")
            relatorio.gerar_detalhes(pasta / "detalhes.pdf", resumo)
            log(f"Dados por extenso: {pasta / 'detalhes.pdf'}")
    finally:
        registro.close()
    return resultado


# ---------- coletas em planilha ----------

def _agenda(serial):
    """Contatos só para dar nome às conversas, quando a cópia dos contatos está desmarcada."""
    try:
        return coleta.contatos(serial)
    except adb.AdbErro:
        return []


def _contatos(serial, pasta_dados, detalhes):
    detalhes["contatos"] = coleta.contatos(serial, pasta_dados)
    quantidade = len(detalhes["contatos"])
    return Etapa(
        "", OK, f"{quantidade} contatos",
        preservado=f"{quantidade} contatos em dados\\contatos.csv",
        legivel=f"{quantidade} contatos (nome e número), também no detalhes.pdf",
        inacessivel="fotos dos contatos e contatos guardados só dentro de apps",
    )


def _sms(serial, pasta_dados, detalhes):
    agenda = detalhes["contatos"] or _agenda(serial)
    detalhes["conversas"], excluidas = coleta.sms(serial, pasta_dados, agenda)
    mensagens = sum(len(c["mensagens"]) for c in detalhes["conversas"])
    fora = sum(excluidas.values())
    return Etapa(
        "", OK,
        f"{len(detalhes['conversas'])} conversas, {mensagens} mensagens com pessoas; "
        f"{fora} mensagens de {len(excluidas)} remetentes excluídas pelo filtro",
        preservado=f"{mensagens} mensagens em dados\\sms.csv e sms.txt",
        legivel=f"{mensagens} mensagens em {len(detalhes['conversas'])} conversas, também no detalhes.pdf",
        inacessivel=(
            f"{fora} mensagens de operadora e serviços excluídas pelo filtro (remetentes em "
            "dados\\sms_filtro.csv); MMS e mensagens de chat (RCS) não são lidas"
        ),
    )


def _chamadas(serial, pasta_dados, detalhes):
    detalhes["chamadas"] = coleta.chamadas(serial, pasta_dados)
    quantidade = len(detalhes["chamadas"])
    return Etapa(
        "", OK, f"{quantidade} chamadas",
        preservado=f"{quantidade} chamadas em dados\\chamadas.csv",
        legivel=f"{quantidade} chamadas (número, nome, data, duração, tipo), também no detalhes.pdf",
        inacessivel="chamadas feitas por apps e registros já apagados do aparelho",
    )


def _apps(serial, pasta_dados, detalhes):
    detalhes["apps"] = coleta.apps(serial, pasta_dados)
    total = len(detalhes["apps"])
    do_usuario = sum(1 for a in detalhes["apps"] if a["origem"].startswith("Instalado"))
    sem_nome = sum(1 for a in detalhes["apps"] if "provável" in a["nome"])
    return Etapa(
        "", OK,
        f"{total} apps: {do_usuario} instalados pelo usuário, {total - do_usuario} de fábrica em uso",
        preservado=f"lista de {total} apps em dados\\apps.csv e histórico bruto em uso_apps_bruto.txt",
        legivel=(
            f"{total} apps com versão, instalação, último uso e tempo de uso; "
            f"{sem_nome} com nome provável (não confirmado na Play Store)"
        ),
        inacessivel="dados internos e logins dos apps; app instalado não prova conta conectada",
    )


def _contas(serial, pasta_dados, contas):
    contas.extend(coleta.contas(serial, pasta_dados))
    return Etapa(
        "", OK, f"{len(contas)} contas",
        preservado=f"{len(contas)} contas registradas em dados\\contas.csv",
        legivel="identificador e tipo de cada conta",
        inacessivel="senhas e tokens não são coletados",
    )


# ---------- WhatsApp ----------

def _etapa_whatsapp(serial, tela, log, etapas):
    log("WhatsApp...")
    tela.progresso(None, "WhatsApp")
    try:
        apps = whatsapp.detectar(serial)
    except adb.AdbErro as e:
        if sem_conexao(e):
            raise ConexaoPerdida(str(e)) from e
        etapas.append(Etapa("WhatsApp", FALHOU, str(e), "whatsapp", inacessivel=f"tudo: {e}"))
        log(f"  FALHOU: {e}")
        return []
    if not apps:
        etapas.append(
            Etapa("WhatsApp", OK, "Nenhum WhatsApp instalado", "whatsapp", inacessivel="não há WhatsApp no aparelho")
        )
        log("  Nenhum WhatsApp instalado")
        return []

    agora = device.hora_do_aparelho(serial)
    fez = tela.confirmar_whatsapp(apps)
    if tela.cancelado():
        raise Cancelado()
    apps = whatsapp.detectar(serial)

    for app in apps:
        recente = (
            app.ultimo_backup is not None
            and agora is not None
            and app.ultimo_backup.timestamp() >= agora - 60
        )
        if recente:
            situacao, detalhe = OK, f"Backup feito agora ({app.backup_texto})"
        elif not fez:
            situacao, detalhe = PARCIAL, f"Backup não foi refeito. Último: {app.backup_texto}"
        else:
            situacao, detalhe = PARCIAL, f"Backup novo não apareceu. Último: {app.backup_texto}"
        etapas.append(Etapa(app.nome, situacao, detalhe, "whatsapp"))
        log(f"  {app.nome}: {detalhe}")
    return apps


def _whatsapp_no_backup(pasta, apps, etapas):
    """Depois da cópia, confere o que de cada WhatsApp ficou de fato na pasta do backup."""
    for app in apps:
        linha = next((e for e in etapas if e.categoria == "whatsapp" and e.nome == app.nome), None)
        if linha is None:
            continue
        copiada = pasta / "arquivos" / Path(*app.pasta.split("/")) if app.pasta else None
        if copiada is None or not copiada.is_dir():
            linha.situacao = FALHOU if linha.situacao == OK else linha.situacao
            linha.preservado = "nada"
            linha.inacessivel = "a pasta do aplicativo não foi copiada"
            continue
        copiados = [p for p in copiada.rglob("*") if p.is_file()]
        bancos = [p for p in copiados if p.name.startswith("msgstore") and ".crypt" in p.name]
        linha.preservado = f"{len(copiados)} arquivos do aplicativo"
        if bancos:
            linha.preservado += f", incluindo {len(bancos)} banco(s) de conversas criptografado(s)"
        else:
            linha.preservado += "; nenhum banco de conversas, porque o aplicativo não tinha backup local"
        linha.legivel = "mídias (fotos, vídeos, áudios e documentos)"
        linha.inacessivel = (
            "texto das conversas: o banco é criptografado e a chave não sai do aparelho. "
            "Para ler, restaure o backup em outro aparelho com o chip da linha"
        )


# ---------- arquivos ----------

def _etapa_arquivos(serial, opcoes, pastas_whatsapp, pasta, tela, log, etapas, copias):
    nome = "Arquivos" if opcoes.arquivos else "Arquivos do WhatsApp"
    log("Medindo os arquivos do celular...")
    tela.progresso(None, "Medindo os arquivos do celular")
    lista = arquivos.origens(serial, tudo=opcoes.arquivos, extras=pastas_whatsapp)
    tamanhos = {o: arquivos.tamanho(serial, o) for o in lista}
    total = sum(tamanhos.values()) or 1

    livre = shutil.disk_usage(pasta).free
    if total > livre:
        etapas.append(
            Etapa(
                nome, FALHOU,
                f"Espaço insuficiente: precisa de {relatorio.tamanho_legivel(total)}, "
                f"há {relatorio.tamanho_legivel(livre)} livres",
                "arquivos", preservado="nada", inacessivel="nenhum arquivo foi copiado por falta de espaço",
            )
        )
        log("  FALHOU: espaço insuficiente no destino")
        return

    usar_tar = arquivos.tem_tar(serial)
    if not usar_tar:
        log("  Aparelho sem tar; usando cópia arquivo por arquivo (mais lenta)")

    copiado = 0

    def ao_copiar(n):
        nonlocal copiado
        copiado += n
        tela.progresso(
            min(copiado / total, 1),
            f"{relatorio.tamanho_legivel(copiado)} de {relatorio.tamanho_legivel(total)}",
        )

    destino = pasta / "arquivos"
    usados = set()
    interrompido = None
    with open(pasta / "manifesto.csv", "w", newline="", encoding="utf-8-sig") as f:
        manifesto = csv.writer(f, delimiter=";")
        manifesto.writerow(["Arquivo", "Tamanho (bytes)", "SHA-256", "Modificado em"])
        try:
            for origem in lista:
                if tela.cancelado():
                    raise Cancelado()
                log(f"Copiando {origem} ({relatorio.tamanho_legivel(tamanhos[origem])})...")
                r = arquivos.copiar(
                    serial, origem, destino, manifesto, ao_copiar, tela.cancelado, usados, usar_tar
                )
                copias.append(r)
                if r.completo:
                    log(f"  {r.arquivos} arquivos")
                else:
                    motivo = r.erro or f"{len(r.falhas)} arquivos não gravados"
                    log(f"  INCOMPLETO: {r.arquivos} de {r.esperados} arquivos ({motivo})")
                    for falha in r.falhas[:20]:
                        log(f"    {falha}")
        except (Cancelado, adb.AdbErro) as e:
            interrompido = e

    feitos = sum(c.arquivos for c in copias)
    esperados = sum(c.esperados for c in copias)
    tamanho = relatorio.tamanho_legivel(sum(c.bytes for c in copias))
    incompletas = [c for c in copias if not c.completo]
    faltaram = [o for o in lista if o not in {c.origem for c in copias}]
    fixo = (
        "dados internos dos apps (/data/data), bloqueados pelo Android sem root; "
        "Android\\obb não é copiado"
    )
    if incompletas or faltaram:
        conferir = ", ".join([c.origem for c in incompletas] + faltaram)
        etapas.append(
            Etapa(
                nome, PARCIAL, f"{feitos} de {esperados} arquivos. Conferir: {conferir}", "arquivos",
                preservado=f"{feitos} arquivos ({tamanho}), com SHA-256 no manifesto.csv",
                legivel="os arquivos copiados abrem direto no computador",
                inacessivel=f"pastas incompletas ou não copiadas: {conferir}; {fixo}",
            )
        )
    else:
        etapas.append(
            Etapa(
                nome, OK, f"{feitos} arquivos, {tamanho}", "arquivos",
                preservado=f"{feitos} arquivos ({tamanho}) de {len(lista)} pastas, com SHA-256 no manifesto.csv",
                legivel="os arquivos abrem direto no computador",
                inacessivel=fixo,
            )
        )
    if isinstance(interrompido, Cancelado):
        raise interrompido
    if interrompido is not None:
        raise ConexaoPerdida(str(interrompido)) from interrompido

"""Cores, fontes e medidas da interface. Tudo em pixels lógicos (o customtkinter aplica a escala)."""
import customtkinter as ctk

# ---------- cores ----------
FUNDO = "#F3F6FA"
SUPERFICIE = "#FFFFFF"
TEXTO = "#182C42"
TEXTO_SECUNDARIO = "#66778A"
TEXTO_APAGADO = "#9AA8B8"
BORDA = "#DFE6EF"
PRINCIPAL = "#0C7482"
PRINCIPAL_SOBRE = "#0A6470"  # botão principal com o mouse em cima
PRINCIPAL_DESLIGADO = "#9CC4CA"
DESTAQUE = "#087E8B"
DESTAQUE_SUAVE = "#E3F2F3"  # fundo do ícone do aparelho
SOBRE_PRINCIPAL = "#FFFFFF"
SELECIONADO = "#EAF6F6"
SELECIONADO_BORDA = "#B5D9DC"
CAMPO = "#FBFCFE"
CAMPO_DESLIGADO = "#F1F4F8"
SUAVE = "#F6F8FB"  # área interna do destino e botões com o mouse em cima
SUCESSO = "#237B5A"
SUCESSO_FUNDO = "#E4F3EC"
AVISO = "#8B620D"
AVISO_FUNDO = "#FFF5DC"
ERRO = "#B32738"
ERRO_FUNDO = "#FBE9EB"
NEUTRO_FUNDO = "#EDF1F6"

# tom -> (texto, fundo), usado em selos e mensagens
TONS = {
    "sucesso": (SUCESSO, SUCESSO_FUNDO),
    "aviso": (AVISO, AVISO_FUNDO),
    "erro": (ERRO, ERRO_FUNDO),
    "neutro": (TEXTO_SECUNDARIO, NEUTRO_FUNDO),
    "andamento": (DESTAQUE, SELECIONADO),
}

# ---------- medidas ----------
MARGEM = 25
ENTRE_BLOCOS = 20
ENTRE_COLUNAS = 18
PADDING_CARTAO = 20
ENTRE_CAMPOS = 14
RAIO_CARTAO = 12
RAIO_CAMPO = 6
RAIO_BOTAO = 8
ALTURA_CAMPO = 38
ALTURA_BOTAO = 40
ALTURA_BOTAO_PRINCIPAL = 44
ALTURA_BARRA_SUPERIOR = 56
LARGURA_COLUNA_DIREITA = 292
ALTURA_PROGRESSO = 6
ALTURA_LOG = 190

JANELA = (1100, 820)
JANELA_MINIMA = (560, 480)
# abaixo disto (largura do conteúdo) os cartões vão para uma coluna só
LARGURA_UMA_COLUNA = 860
# abaixo disto os pares de campos e de opções empilham
LARGURA_CAMPOS_EMPILHADOS = 600

_FAMILIA = "Segoe UI"
_FAMILIA_FORTE = "Segoe UI Semibold"
_FAMILIA_LOG = "Consolas"

_fontes = {}


def reiniciar():
    """As fontes pertencem à janela em que foram criadas; janela nova, fontes novas."""
    _fontes.clear()


def fonte(nome):
    """Fontes criadas sob demanda, porque precisam da janela já aberta."""
    if not _fontes:
        _fontes.update(
            titulo=ctk.CTkFont(_FAMILIA_FORTE, 27),
            marca=ctk.CTkFont(_FAMILIA_FORTE, 15),
            sobretitulo=ctk.CTkFont(_FAMILIA_FORTE, 11),
            subtitulo=ctk.CTkFont(_FAMILIA, 14),
            cartao=ctk.CTkFont(_FAMILIA_FORTE, 15),
            aparelho=ctk.CTkFont(_FAMILIA_FORTE, 15),
            normal=ctk.CTkFont(_FAMILIA, 13),
            forte=ctk.CTkFont(_FAMILIA_FORTE, 13),
            rotulo=ctk.CTkFont(_FAMILIA_FORTE, 12),
            ajuda=ctk.CTkFont(_FAMILIA, 12),
            pequena=ctk.CTkFont(_FAMILIA, 11),
            botao=ctk.CTkFont(_FAMILIA, 14),
            botao_principal=ctk.CTkFont(_FAMILIA_FORTE, 14),
            log=ctk.CTkFont(_FAMILIA_LOG, 12),
        )
    return _fontes[nome]

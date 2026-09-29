"""Ícones de traço fino desenhados pelo próprio programa (sem arquivos nem internet).

Cada ícone é uma lista de formas numa grade de 24 x 24. O desenho é feito em
tamanho grande e reduzido, para o traço sair suave em qualquer escala do Windows.
"""
import math

import customtkinter as ctk
from PIL import Image, ImageDraw

_GRADE = 24
_AMPLIACAO = 16
_TRACO = 1.7

# formas: ("linha", pontos) | ("ret", x, y, largura, altura, raio) | ("circ", cx, cy, r)
#         ("arco", cx, cy, r, inicio, fim) em graus, sentido horário a partir das 3 horas
#         ("cheio", cx, cy, r)
DESENHOS = {
    "arquivo": [
        ("ret", 3, 4, 18, 4.5, 1),
        ("linha", [(5, 8.5), (5, 19), (6, 20), (18, 20), (19, 19), (19, 8.5)]),
        ("linha", [(10, 12.5), (14, 12.5)]),
    ],
    "celular": [("ret", 7, 2.5, 10, 19, 2), ("linha", [(11.2, 17.5), (12.8, 17.5)])],
    "identificar": [
        ("linha", [(3, 7), (3, 4.5), (4.5, 3), (7, 3)]),
        ("linha", [(17, 3), (19.5, 3), (21, 4.5), (21, 7)]),
        ("linha", [(21, 17), (21, 19.5), (19.5, 21), (17, 21)]),
        ("linha", [(7, 21), (4.5, 21), (3, 19.5), (3, 17)]),
        ("linha", [(7, 12), (17, 12)]),
    ],
    "pessoa": [("circ", 12, 8, 4), ("arco", 12, 21.5, 7.5, 180, 360)],
    "pasta": [
        ("linha", [(3, 7), (3, 18), (4.5, 19.5), (19.5, 19.5), (21, 18), (21, 9.5), (19.5, 8),
                   (12.5, 8), (10.5, 5), (4.5, 5), (3, 6.5), (3, 7)]),
    ],
    "preparar": [("circ", 12, 12, 9), ("linha", [(10, 8.5), (15.5, 12), (10, 15.5), (10, 8.5)])],
    "copiar": [("ret", 9, 9, 12, 12, 2), ("linha", [(15, 5), (14, 4), (5.5, 4), (4, 5.5), (4, 14), (5, 15)])],
    "midias": [
        ("ret", 3, 3, 18, 18, 2),
        ("circ", 9, 9, 1.8),
        ("linha", [(21, 15), (16.5, 10.5), (6, 21)]),
    ],
    "conversa": [
        ("arco", 12, 11.5, 8.5, 155, 475),
        ("linha", [(8.4, 19.2), (3.6, 20.4), (4.3, 15.1)]),
    ],
    "contatos": [
        ("ret", 4, 3, 16, 18, 2),
        ("circ", 12, 10, 2.6),
        ("arco", 12, 19.5, 4.6, 200, 340),
    ],
    "mensagem": [
        ("linha", [(4, 5.5), (5.5, 4), (18.5, 4), (20, 5.5), (20, 14.5), (18.5, 16), (9, 16),
                   (4, 20), (4, 5.5)]),
        ("linha", [(8, 8.5), (16, 8.5)]),
        ("linha", [(8, 12), (13, 12)]),
    ],
    "telefone": [
        ("linha", [(4.6, 5.2), (7.6, 3.6), (10, 8), (8.2, 9.8), (14.2, 15.8), (16, 14),
                   (20.4, 16.4), (18.8, 19.4), (15.4, 20.2), (8.4, 15.6), (4, 8.8), (4.6, 5.2)]),
    ],
    "apps": [
        ("ret", 4, 4, 6.5, 6.5, 1.2), ("ret", 13.5, 4, 6.5, 6.5, 1.2),
        ("ret", 4, 13.5, 6.5, 6.5, 1.2), ("ret", 13.5, 13.5, 6.5, 6.5, 1.2),
    ],
    "baixar": [
        ("linha", [(12, 3.5), (12, 15)]),
        ("linha", [(7, 10), (12, 15), (17, 10)]),
        ("linha", [(4, 17), (4, 19), (5.5, 20.5), (18.5, 20.5), (20, 19), (20, 17)]),
    ],
    "seta": [("linha", [(5, 12), (19, 12)]), ("linha", [(13, 6), (19, 12), (13, 18)])],
    "terminal": [("linha", [(4, 7), (9.5, 12), (4, 17)]), ("linha", [(12, 18), (20, 18)])],
    "abaixo": [("linha", [(6, 9), (12, 15), (18, 9)])],
    "acima": [("linha", [(6, 15), (12, 9), (18, 15)])],
    "usb": [
        ("ret", 8.5, 2.5, 7, 5.5, 1),
        ("linha", [(6, 8), (18, 8), (18, 12.5), (15, 16.5), (9, 16.5), (6, 12.5), (6, 8)]),
        ("linha", [(12, 16.5), (12, 21.5)]),
    ],
    "ponto": [("cheio", 12, 12, 5)],
    "pendente": [("circ", 12, 12, 4.6)],
    "pronto": [("cheio", 12, 12, 5.4)],
    "alerta": [
        ("linha", [(12, 3.5), (21, 19.5), (3, 19.5), (12, 3.5)]),
        ("linha", [(12, 10), (12, 14)]),
        ("linha", [(12, 17), (12, 17.2)]),
    ],
}

_prontos = {}


def desenhar(nome, cor, traco=_TRACO):
    """Imagem grande (RGBA) do ícone, para ser reduzida ao tamanho de uso."""
    e = _AMPLIACAO
    lado = _GRADE * e
    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    pincel = ImageDraw.Draw(imagem)
    grossura = max(1, round(traco * e))
    meio = grossura / 2

    def ponta(x, y):
        pincel.ellipse((x * e - meio, y * e - meio, x * e + meio, y * e + meio), fill=cor)

    for forma in DESENHOS[nome]:
        tipo = forma[0]
        if tipo == "linha":
            pontos = [(x * e, y * e) for x, y in forma[1]]
            pincel.line(pontos, fill=cor, width=grossura, joint="curve")
            for x, y in forma[1]:
                ponta(x, y)  # cantos e pontas arredondados
        elif tipo == "ret":
            _, x, y, largura, altura, raio = forma
            pincel.rounded_rectangle(
                (x * e - meio, y * e - meio, (x + largura) * e + meio, (y + altura) * e + meio),
                radius=raio * e + meio, outline=cor, width=grossura,
            )
        elif tipo == "circ":
            _, cx, cy, r = forma
            pincel.ellipse(
                ((cx - r) * e - meio, (cy - r) * e - meio, (cx + r) * e + meio, (cy + r) * e + meio),
                outline=cor, width=grossura,
            )
        elif tipo == "arco":
            _, cx, cy, r, inicio, fim = forma
            pincel.arc(
                ((cx - r) * e - meio, (cy - r) * e - meio, (cx + r) * e + meio, (cy + r) * e + meio),
                inicio, fim, fill=cor, width=grossura,
            )
            for angulo in (inicio, fim):
                ponta(cx + r * math.cos(math.radians(angulo)), cy + r * math.sin(math.radians(angulo)))
        elif tipo == "cheio":
            _, cx, cy, r = forma
            pincel.ellipse(((cx - r) * e, (cy - r) * e, (cx + r) * e, (cy + r) * e), fill=cor)
    return imagem


def reiniciar():
    """As imagens pertencem à janela em que foram criadas; janela nova, imagens novas."""
    _prontos.clear()


def icone(nome, cor, tamanho=18, traco=_TRACO):
    chave = (nome, cor, tamanho, traco)
    if chave not in _prontos:
        _prontos[chave] = ctk.CTkImage(desenhar(nome, cor, traco), size=(tamanho, tamanho))
    return _prontos[chave]

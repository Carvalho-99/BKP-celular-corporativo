"""Abre a janela real com dados fictícios e salva uma imagem dela, para conferir o visual.

Uso: .venv\\Scripts\\python tests\\captura_de_tela.py saida.png [largura altura] [opções]
  --vazio      nenhum aparelho no cabo
  --conflito   aparelho com dois nomes possíveis para o funcionário
  --troca      outro aparelho conectado com dados do anterior na tela
  --varios     dois aparelhos no cabo
  --iphone     iPhone detectado
  --recusa     aparelho que recusa a leitura de SMS
  --fim        rola até o fim da tela        --log   abre os detalhes da execução
Nada é lido de celular nem gravado.
"""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import customtkinter as ctk  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from backup import conectores  # noqa: E402
from interface import janela  # noqa: E402
from test_interface import A15, A16, IPHONE, cobertura_de, identificacao_de  # noqa: E402

DOIS_NOMES = (
    ("Maria Souza", "e-mail corporativo maria.souza@forest.ind.br"),
    ("João Pedro", "nome dado ao aparelho (“A15 de João Pedro”)"),
)


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    opcoes = {a for a in sys.argv[1:] if a.startswith("--")}
    saida = argumentos[0]
    no_cabo = [A15]
    if "--vazio" in opcoes:
        no_cabo = []
    elif "--varios" in opcoes:
        no_cabo = [A15, A16]
    elif "--iphone" in opcoes:
        no_cabo = [IPHONE]
    candidatos = DOIS_NOMES if "--conflito" in opcoes else (("João Silva", "e-mail corporativo joao.silva@forest.ind.br"),)
    recusadas = ("sms",) if "--recusa" in opcoes else ()

    substitutos = [
        (conectores, "listar", lambda com_iphone=True: list(no_cabo)),
        (conectores, "listar_iphones", lambda: []),
        (conectores, "identificar", lambda a: identificacao_de(a, candidatos)),
        (conectores, "levantar_cobertura", lambda a: cobertura_de(a, recusadas)),
        (janela, "ler_config", lambda: {"tecnico": "Ana Lima", "destino": "D:\\Backups de celulares"}),
        (janela.estado, "problema_no_destino", lambda destino: ""),  # a pasta fictícia não existe
    ]
    for alvo, nome, substituto in substitutos:
        mock.patch.object(alvo, nome, substituto).start()

    raiz = ctk.CTk()
    tela = janela.Janela(raiz)
    if len(argumentos) >= 3:
        raiz.geometry(f"{argumentos[1]}x{argumentos[2]}+40+20")
    raiz.attributes("-topmost", True)
    if "--log" in opcoes:
        tela.painel_log.alternar()
    if "--troca" in opcoes:
        raiz.after(1500, lambda: (no_cabo.__setitem__(slice(None), [A16]), tela._recebeu_aparelhos([A16])))

    def fotografar():
        if "--fim" in opcoes:
            tela.rolagem._parent_canvas.yview_moveto(1)
        raiz.update()
        x, y = raiz.winfo_rootx(), raiz.winfo_rooty()
        ImageGrab.grab((x, y, x + raiz.winfo_width(), y + raiz.winfo_height())).save(saida)
        raiz.destroy()

    raiz.after(3000, fotografar)
    raiz.mainloop()


if __name__ == "__main__":
    main()

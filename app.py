"""Backup de celular corporativo - ponto de entrada."""
import sys


def autoteste():
    """Confere, sem abrir a tela para uso, se o programa está inteiro. Usado depois de gerar o .exe.

    Grava o resultado em autoteste.txt na pasta de dados e devolve 0 se tudo funcionou.
    """
    import traceback

    from backup import locais

    locais.preparar()
    linhas, falhas = [f"executavel: {locais.EXECUTAVEL}", f"dados: {locais.DADOS}"], 0

    def conferir(nome, funcao):
        nonlocal falhas
        try:
            linhas.append(f"OK     {nome}: {funcao()}")
        except Exception:  # noqa: BLE001 - o autoteste registra qualquer erro
            falhas += 1
            linhas.append(f"FALHOU {nome}: {traceback.format_exc(limit=3)}")

    def adb_responde():
        from backup import adb
        return adb.executar(["version"], timeout=30).splitlines()[0]

    def aparelhos():
        from backup import conectores
        return [(a.plataforma, a.estado) for a in conectores.listar()]

    def tela():
        import customtkinter as ctk
        from interface import janela
        raiz = ctk.CTk()
        raiz.withdraw()
        janela.Janela(raiz)
        raiz.update()
        raiz.destroy()
        return "montada"

    def pdf():
        from backup.relatorio import _Pdf
        documento = _Pdf()
        documento.add_page()
        documento.paragrafo("teste de acentuação")
        return f"{len(documento.output())} bytes"

    conferir("adb", adb_responde)
    conferir("aparelhos no cabo", aparelhos)
    conferir("icone", lambda: locais.ICONE.exists())
    conferir("pdf", pdf)
    conferir("tela", tela)
    (locais.DADOS / "autoteste.txt").write_text("\n".join(linhas), encoding="utf-8")
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())
    from interface.janela import abrir

    abrir()

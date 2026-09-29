"""Mostra o que o programa consegue ler do aparelho que está no cabo, sem fazer backup.

Serve para validar um modelo novo de celular. Os valores aparecem mascarados
e nenhuma mensagem ou contato é impresso, só contagens.
Uso: .venv\\Scripts\\python diagnostico.py
"""
import io
import re
import sys
import tarfile
import time

from backup import adb, arquivos, captura, cobertura, coleta, conectores


def mascarar(texto):
    """Esconde o meio de números e e-mails: dá para conferir sem expor o dado."""
    texto = re.sub(r"[\w.+-]+@", lambda m: m.group()[:3] + "***@", str(texto))
    return re.sub(r"\d(?=\d{3})", "#", texto)


def testar(nome, funcao):
    inicio = time.time()
    try:
        resultado, situacao = funcao(), "OK    "
    except Exception as e:  # noqa: BLE001 - o diagnóstico mostra qualquer erro
        resultado, situacao = f"{type(e).__name__}: {e}", "FALHOU"
    print(f"  [{situacao}] {nome}: {resultado}  ({time.time() - inicio:.1f}s)")


def fluxo_unico(serial):
    """Puxa por tar, em memória, a pasta pequena com mais arquivos, para validar o mecanismo."""
    if not arquivos.tem_tar(serial):
        return "aparelho sem tar; o backup usará cópia arquivo por arquivo"
    pastas = arquivos.origens(serial)
    tamanhos = {p: arquivos.tamanho(serial, p) for p in pastas}
    quantidades = {p: arquivos.contar(serial, p) for p in pastas if tamanhos[p] < 200 * 1024 * 1024}
    candidatas = [p for p, n in quantidades.items() if n > 0]
    if not candidatas:
        return f"tar existe; nenhuma pasta pequena com arquivos para testar ({len(pastas)} pastas)"
    pasta = max(candidatas, key=quantidades.get)
    processo = adb.stream(f"cd /sdcard && tar -cf - {adb.aspas('./' + pasta)} 2>/dev/null", serial)
    dados = processo.stdout.read()
    processo.wait()
    with tarfile.open(fileobj=io.BytesIO(dados), mode="r|") as tar:
        lidos = sum(1 for membro in tar if membro.isfile())
    return f"pasta '{pasta}': {lidos} de {quantidades[pasta]} arquivos lidos ({len(dados) / 1024:.0f} KB)"


def contagem(serial, uri, colunas):
    return f"{len(coleta.consultar(serial, uri, colunas))} registros"


def principal():
    aparelhos = conectores.listar()
    print("Aparelhos no cabo:")
    for a in aparelhos:
        print(f"  {a.plataforma}: {a.modelo or '(sem nome)'} | identificador {mascarar(a.id)} | estado {a.estado}")
    prontos = [a for a in aparelhos if a.estado == conectores.PRONTO]
    if len(prontos) != 1:
        sys.exit("Precisa de exatamente um Android conectado e autorizado.")
    serial = prontos[0].id

    inicio = time.time()
    identificacao = captura.identificar(serial)
    print(f"\nIdentificação de {identificacao.titulo} ({time.time() - inicio:.1f}s)")
    grupo = None
    for l in identificacao.leituras:
        if l.grupo != grupo:
            grupo = l.grupo
            print(f"\n  [{grupo}]")
        detalhe = mascarar(l.valor) if l.coletada else "motivo: " + mascarar(l.motivo)
        print(f"    {l.situacao:16} {l.item}: {detalhe}")
        print(f"    {'':16} via {mascarar(l.metodo)}")
    print("\n  Sugestões de funcionário:")
    for c in identificacao.candidatos:
        print(f"    {c.nome} (por {mascarar('; '.join(c.fontes))})")
    if not identificacao.candidatos:
        print("    nenhuma")
    print("  Campos que seriam preenchidos:", ", ".join(identificacao.campos) or "nenhum")

    print("\nO que o aparelho permite copiar:")
    for c in cobertura.android(serial).values():
        print(f"  {c.nome}: {c.situacao}. {c.resumo}")

    print("\nLeituras usadas no backup (só contagens):")
    testar("SMS", lambda: contagem(serial, "content://sms", ["address", "date", "type", "body"]))
    testar("Contatos", lambda: contagem(serial, "content://com.android.contacts/data/phones", ["data1", "display_name"]))
    testar("Chamadas", lambda: contagem(serial, "content://call_log/calls", ["number", "date", "duration", "type", "name"]))
    testar("Cópia em fluxo único", lambda: fluxo_unico(serial))


if __name__ == "__main__":
    principal()

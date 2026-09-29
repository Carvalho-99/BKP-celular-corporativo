"""Detecção do WhatsApp / WhatsApp Business e do último backup local."""
from dataclasses import dataclass
from datetime import datetime

from . import adb

# pacote -> (nome, pastas possíveis relativas a /sdcard, da mais nova para a mais antiga)
APPS = {
    "com.whatsapp": ("WhatsApp", ["Android/media/com.whatsapp/WhatsApp", "WhatsApp"]),
    "com.whatsapp.w4b": (
        "WhatsApp Business",
        ["Android/media/com.whatsapp.w4b/WhatsApp Business", "WhatsApp Business"],
    ),
}

PASSOS_BACKUP = (
    "No celular, abra o {nome}:\n"
    "  1. Toque nos três pontinhos > Configurações\n"
    "  2. Conversas > Backup de conversas\n"
    "  3. Anote a conta do Google que aparece ali\n"
    "  4. Toque em FAZER BACKUP e espere terminar"
)


@dataclass
class App:
    pacote: str
    nome: str
    pasta: str = ""
    ultimo_backup: datetime | None = None
    arquivo: str = ""

    @property
    def backup_texto(self):
        if not self.ultimo_backup:
            return "Nenhum backup local encontrado"
        return self.ultimo_backup.strftime("%d/%m/%Y %H:%M")


def detectar(serial):
    instalados = adb.shell("pm list packages", serial, timeout=120).splitlines()
    instalados = {linha.split(":", 1)[1].strip() for linha in instalados if ":" in linha}
    encontrados = []
    for pacote, (nome, pastas) in APPS.items():
        if pacote not in instalados:
            continue
        app = App(pacote=pacote, nome=nome)
        for pasta in pastas:
            if adb.shell(f"[ -d {adb.aspas('/sdcard/' + pasta)} ] && echo sim", serial).strip() == "sim":
                app.pasta = pasta
                _ler_ultimo_backup(serial, app)
                break
        encontrados.append(app)
    return encontrados


def _ler_ultimo_backup(serial, app):
    # o curinga fica fora das aspas para o shell do celular expandir
    padrao = adb.aspas(f"/sdcard/{app.pasta}/Databases") + "/msgstore*.crypt*"
    saida = adb.shell(f"stat -c '%Y %n' {padrao} 2>/dev/null", serial)
    mais_novo = 0
    for linha in saida.splitlines():
        momento, _, nome = linha.partition(" ")
        if momento.isdigit() and int(momento) > mais_novo:
            mais_novo = int(momento)
            app.arquivo = nome.rsplit("/", 1)[-1]
    if mais_novo:
        app.ultimo_backup = datetime.fromtimestamp(mais_novo)

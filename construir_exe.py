"""Gera o executável do programa em dist\\Backup Corporativo.exe.

Uso: .venv\\Scripts\\python construir_exe.py
Precisa do PyInstaller (.venv\\Scripts\\pip install pyinstaller) e do ADB em tools\\platform-tools.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJETO = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJETO))

from backup import locais  # noqa: E402
from interface import icones, tema  # noqa: E402

# do ADB só vai o necessário; o resto do platform-tools (fastboot etc.) não é usado
ARQUIVOS_DO_ADB = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "libwinpthread-1.dll")


def gerar_icone(destino):
    """Mesmo desenho da marca na barra do programa: caixa branca sobre quadrado azul-petróleo."""
    lado = 256
    fundo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(fundo).rounded_rectangle((8, 8, lado - 8, lado - 8), radius=56, fill=tema.PRINCIPAL)
    caixa = icones.desenhar("arquivo", tema.SOBRE_PRINCIPAL, traco=1.9).resize((150, 150), Image.LANCZOS)
    fundo.alpha_composite(caixa, ((lado - 150) // 2, (lado - 150) // 2))
    destino.parent.mkdir(parents=True, exist_ok=True)
    fundo.save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def separar_adb(destino):
    origem = PROJETO / "tools" / "platform-tools"
    if not (origem / "adb.exe").exists():
        sys.exit(f"ADB não encontrado em {origem}. Veja o README.")
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    for nome in ARQUIVOS_DO_ADB:
        if (origem / nome).exists():
            shutil.copy2(origem / nome, destino / nome)


def main():
    montagem = PROJETO / "build"
    icone = PROJETO / "recursos" / "icone.ico"
    adb = montagem / "platform-tools"
    gerar_icone(icone)
    separar_adb(adb)
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", locais.NOME,
        "--icon", str(icone),
        "--distpath", str(PROJETO / "dist"),
        "--workpath", str(montagem / "pyinstaller"),
        "--specpath", str(montagem),
        "--collect-data", "customtkinter",
        "--add-data", f"{icone};recursos",
        "--add-data", f"{adb};platform-tools",
        str(PROJETO / "app.py"),
    ]
    subprocess.run(comando, check=True, cwd=PROJETO)
    executavel = PROJETO / "dist" / f"{locais.NOME}.exe"
    print(f"\nGerado: {executavel} ({executavel.stat().st_size / 1024 ** 2:.1f} MB)")


if __name__ == "__main__":
    main()

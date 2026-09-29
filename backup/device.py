"""Identificação do aparelho conectado."""
import re

from . import adb

_PROP = re.compile(r"^\[(.+?)\]: \[(.*)\]$")


def info(serial):
    props = {}
    for linha in adb.shell("getprop", serial).splitlines():
        m = _PROP.match(linha.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return {
        "fabricante": props.get("ro.product.manufacturer", "").title(),
        "modelo": props.get("ro.product.model", ""),
        "android": props.get("ro.build.version.release", ""),
        "patch": props.get("ro.build.version.security_patch", ""),
        "serial": props.get("ro.serialno") or serial,
    }


def hora_do_aparelho(serial):
    """Relógio do celular em segundos (epoch); None se não der para ler."""
    saida = adb.shell("date +%s", serial).strip()
    return int(saida) if saida.isdigit() else None

from .common import upper_safe

BANK_SLUG = {
    "Banco de la Nación Argentina": "nacion",
    "Banco de Santa Fe": "santafe",
    "Banco Macro": "macro",
    "Banco Santander": "santander",
    "Banco Galicia": "galicia",
}

# Hints
BNA_NAME_HINT = "BANCO DE LA NACION ARGENTINA"
BANK_MACRO_HINTS   = ("BANCO MACRO","CUENTA CORRIENTE BANCARIA","SALDO ULTIMO EXTRACTO AL","DEBITO FISCAL IVA BASICO","N/D DBCR 25413")
BANK_SANTAFE_HINTS = ("BANCO DE SANTA FE","NUEVO BANCO DE SANTA FE","SALDO ANTERIOR","IMPTRANS","IVA GRAL")
BANK_NACION_HINTS  = (BNA_NAME_HINT, "SALDO ANTERIOR", "SALDO FINAL", "I.V.A. BASE", "COMIS.")
BANK_GALICIA_HINTS = ("BANCO GALICIA","RESUMEN DE CUENTA","SIRCREB","IMP. DEB./CRE. LEY 25413","TRANSFERENCIA DE TERCEROS")

def detect_bank_from_text(txt: str) -> str:
    U = upper_safe(txt)
    scores = {
        "Banco Macro": sum(1 for k in BANK_MACRO_HINTS if k in U),
        "Banco de Santa Fe": sum(1 for k in BANK_SANTAFE_HINTS if k in U),
        "Banco de la Nación Argentina": sum(1 for k in BANK_NACION_HINTS if k in U),
        "Banco Galicia": sum(1 for k in BANK_GALICIA_HINTS if k in U),
        "Banco Santander": (1 if "SANTANDER" in U else 0) + (1 if "DETALLE IMPOSITIVO" in U else 0),
    }
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "Banco no identificado"

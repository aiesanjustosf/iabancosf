
import re
from .utils import ar_to_float, normalize_whitespace, concilia, build_df

KEY_CRED = re.compile(r"(dep|transf|acred|credito|ingreso|^haber\b)", re.I)
KEY_DEB  = re.compile(r"(debito|pago|serv|extrac|compra|^debe\b)", re.I)

def parse_generico(pages_text: list[str]):
    rows = []
    total_debitos = 0.0
    total_creditos = 0.0
    saldo_inicial = 0.0
    saldo_pdf = 0.0

    full = "\n".join(pages_text)

    # saldo inicial/final
    m0 = re.search(r"Saldo\s+inicial.*?\$?\s*([-\d\.\,]+)", full, re.I)
    if m0: saldo_inicial = ar_to_float(m0.group(1))
    m1 = re.search(r"Saldo\s+final.*?\$?\s*([-\d\.\,]+)", full, re.I)
    if m1: saldo_pdf = ar_to_float(m1.group(1))

    for page in pages_text:
        for raw in page.splitlines():
            s = normalize_whitespace(raw)
            if not re.search(r"\b\d{2}/\d{2}\b", s):
                continue
            mm = re.findall(r"[-]?\$?\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})", s)
            if not mm: 
                continue
            monto = ar_to_float(mm[-1])

            # Heurística: si dice "saldo anterior", la próxima línea determina el signo inverso para cuadrar
            if re.search(r"saldo\s+anterior", s, re.I):
                rows.append([s[:5], s, 0.0, 0.0, 0.0, 0.0, None])
                continue

            if KEY_DEB.search(s) and not KEY_CRED.search(s):
                debito = abs(monto)
                credito = 0.0
            elif KEY_CRED.search(s) and not KEY_DEB.search(s):
                debito = 0.0
                credito = abs(monto)
            else:
                # fallback: signo negativo => débito
                if "-" in s:
                    debito = abs(monto); credito = 0.0
                else:
                    credito = abs(monto); debito = 0.0

            total_debitos += debito
            total_creditos += credito
            rows.append([s[:5], s, debito, credito, credito-debito, monto, None])

    ok, calculado, diff = concilia(saldo_inicial, total_creditos, total_debitos, saldo_pdf)
    df = build_df(rows)
    resumen = {
        "saldo_inicial": saldo_inicial,
        "total_creditos": total_creditos,
        "total_debitos": total_debitos,
        "saldo_pdf": saldo_pdf,
        "cuadra": ok,
        "saldo_calc": calculado,
        "diferencia": diff,
        "parser": "generico",
    }
    return resumen, df

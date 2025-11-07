
import re
import pandas as pd

CURRENCY_RE = re.compile(r"[-]?\$?\s*\d{1,3}(\.\d{3})*(,\d{2})?")

def ar_to_float(x: str) -> float:
    if x is None:
        return 0.0
    s = str(x).strip()
    s = s.replace("$", "").replace(" ", "")
    # signo
    neg = s.startswith("-")
    s = s.replace("-", "")
    # puntos de miles
    s = s.replace(".", "")
    # coma decimal
    s = s.replace(",", ".")
    try:
        v = float(s)
    except Exception:
        v = 0.0
    return -v if neg else v

def normalize_whitespace(line: str) -> str:
    return " ".join(str(line).split())

def concilia(saldo_inicial: float, total_creditos: float, total_debitos: float, saldo_pdf: float, tol: float = 0.01):
    calculado = saldo_inicial + total_creditos - total_debitos
    diff = round(calculado - saldo_pdf, 2)
    return abs(diff) <= tol, calculado, diff

def build_df(rows):
    df = pd.DataFrame(rows, columns=["fecha","descripcion","debito","credito","importe","monto_pdf","saldo"])
    for col in ["debito","credito","importe","monto_pdf","saldo"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    return df

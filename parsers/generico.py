import pandas as pd
import numpy as np
from .common import (
    MONEY_RE, DATE_RE, extract_all_lines, normalize_money, normalize_desc,
    find_saldo_final_from_lines, find_saldo_anterior_from_lines, clasificar
)

def santander_cut_before_detalle(all_lines: list[str]) -> list[str]:
    cut = len(all_lines)
    for i, ln in enumerate(all_lines):
        if "DETALLE IMPOSITIVO" in (ln or "").upper():
            cut = i
            break
    return all_lines[:cut]

def parse_lines_generic(lines) -> pd.DataFrame:
    rows = []; seq = 0
    for ln in lines:
        s = (ln or "").strip()
        if not s: 
            continue
        # Excluir headers comunes
        if ("FECHA" in s.upper() and ("SALDO" in s.upper() or "DÉBITO" in s.upper() or "DEBITO" in s.upper())):
            pass  # no return; dejar pasar si tiene montos
        am = list(MONEY_RE.finditer(s))
        if len(am) < 2:
            continue
        d = DATE_RE.search(s)
        if not d or d.end() >= am[0].start():
            continue

        saldo = normalize_money(am[-1].group(0))
        monto = normalize_money(am[-2].group(0))
        desc  = s[d.end(): am[0].start()].strip()
        seq += 1
        rows.append({
            "fecha": pd.to_datetime(d.group(0), dayfirst=True, errors="coerce"),
            "descripcion": desc,
            "origen": None,
            "desc_norm": normalize_desc(desc),
            "debito": 0.0, "credito": 0.0,
            "importe": 0.0, "monto_pdf": monto, "saldo": saldo, "orden": seq
        })
    return pd.DataFrame(rows)

def parse_pdf_generico(bank_name: str, file_like, maybe_lines: list[str] | None = None):
    if maybe_lines is None:
        lines = [l for _, l in extract_all_lines(file_like)]
    else:
        lines = maybe_lines

    df = parse_lines_generic(lines).sort_values(["fecha","orden"]).reset_index(drop=True)

    # saldo final e inicial
    fecha_cierre, saldo_final_pdf = find_saldo_final_from_lines(lines)
    saldo_anterior = find_saldo_anterior_from_lines(lines)

    # reconstrucción débito/crédito por delta de saldo
    if not df.empty:
        # Insertar SALDO ANTERIOR si existe
        saldo_inicial = np.nan
        if not np.isnan(saldo_anterior):
            saldo_inicial = float(saldo_anterior)
        elif pd.notna(df.loc[0, "saldo"]) and len(df) > 1:
            # usar delta del primer movimiento para estimar saldo inicial si no hay etiqueta
            # saldo_inicial = saldo(primera fila) - delta_saldo(primera fila)
            pass

        # delta y asignación
        df["delta_saldo"] = df["saldo"].diff()
        # Si la primer fila no tiene delta, intentar inferir con monto_pdf (si el banco la provee)
        if pd.isna(df.loc[0, "delta_saldo"]):
            m0 = float(df.loc[0, "monto_pdf"])
            # si el banco no separa débito/crédito, usar regla: saldo nuevo = saldo_inicial + (cr) - (db)
            # No conocemos saldo_inicial: dejamos delta como m0 y que el signo determine
            df.loc[0, "delta_saldo"] = m0

        df["debito"]  = np.where(df["delta_saldo"] < 0, -df["delta_saldo"], 0.0)
        df["credito"] = np.where(df["delta_saldo"] > 0,  df["delta_saldo"], 0.0)
        df["importe"] = df["credito"] - df["debito"]

        if not np.isnan(saldo_inicial):
            first_date = df["fecha"].dropna().min()
            apertura = pd.DataFrame([{
                "fecha": (first_date - pd.Timedelta(days=1)) if pd.notna(first_date) else pd.NaT,
                "descripcion": "SALDO ANTERIOR",
                "origen": None,
                "desc_norm": "SALDO ANTERIOR",
                "debito": 0.0, "credito": 0.0,
                "importe": 0.0, "monto_pdf": 0.0,
                "saldo": float(saldo_inicial),
                "orden": 0, "delta_saldo": np.nan
            }])
            df = pd.concat([apertura, df], ignore_index=True).sort_values(["fecha","orden"]).reset_index(drop=True)

    # Clasificación
    df["Clasificación"] = df.apply(
        lambda r: clasificar(str(r.get("descripcion","")), str(r.get("desc_norm","")), r.get("debito",0.0), r.get("credito",0.0)),
        axis=1
    )

    fecha_cierre_str = fecha_cierre.strftime('%d/%m/%Y') if pd.notna(fecha_cierre) else None
    # Quitar columnas internas
    for c in ("orden","monto_pdf","delta_saldo"):
        if c in df.columns: df = df.drop(columns=[c])
    return df, fecha_cierre_str

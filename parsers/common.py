import io, re
import numpy as np
import pandas as pd
import streamlit as st
import pdfplumber

MONEY_RE = re.compile(r'(?<!\S)-?(?:\d{1,3}(?:\.\d{3})*|\d+)\s?,\s?\d{2}-?(?!\S)')
DATE_RE  = re.compile(r"\b\d{1,2}/\d{2}/\d{2,4}\b")

def normalize_money(tok: str) -> float:
    if not tok:
        return np.nan
    s = tok.strip()
    neg = s.endswith("-") or s.startswith("-")
    s = s.lstrip("-").rstrip("-")
    if "," not in s: return np.nan
    main, frac = s.rsplit(",", 1)
    try:
        val = float(f"{main.replace('.','').replace(' ','')}.{frac}")
        return -val if neg else val
    except Exception:
        return np.nan

def fmt_ar(n) -> str:
    if n is None or (isinstance(n, float) and (np.isnan(n))):
        return "—"
    return f"{n:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")

def extract_all_lines(b: bytes):
    out = []
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for pi, p in enumerate(pdf.pages, start=1):
            txt = (p.extract_text() or "")
            for ln in txt.splitlines():
                ln = " ".join(ln.split())
                if ln:
                    out.append((pi, ln))
    return out

def parse_generic_table(lines):
    """Genérico: dd/mm/aa ... $ ... $ ... -> último $ = saldo; penúltimo = movim signado."""
    rows, seq = [], 0
    for _, ln in lines:
        am = list(MONEY_RE.finditer(ln))
        if len(am) < 2:
            continue
        d = DATE_RE.search(ln)
        if not d or d.end() >= am[0].start():
            continue
        saldo = normalize_money(am[-1].group(0))
        mov   = normalize_money(am[-2].group(0))
        desc  = ln[d.end():am[0].start()].strip()
        seq += 1
        rows.append({
            "fecha": pd.to_datetime(d.group(0), dayfirst=True, errors="coerce"),
            "descripcion": desc,
            "monto_pdf": mov,
            "saldo": saldo,
            "orden": seq,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["fecha", "orden"]).reset_index(drop=True)
    return df

def render_summary(df, saldo_inicial=None, saldo_final_pdf=None, titulo="CUENTA · Nro s/n"):
    st.subheader(titulo)
    if df.empty:
        st.info("No se detectaron líneas de movimientos en la tabla.")
        return

    # Si no pasaron saldos, estimamos
    if saldo_inicial is None:
        # Asumimos primer saldo y primer movimiento para reconstruir el inicial (fallback)
        s0 = float(df.loc[0, "saldo"])
        m0 = float(df.loc[0, "monto_pdf"])
        saldo_inicial = s0 - m0

    debitos  = float(np.where(df["monto_pdf"] < 0, -df["monto_pdf"], 0.0).sum())
    creditos = float(np.where(df["monto_pdf"] > 0,  df["monto_pdf"], 0.0).sum())

    saldo_final_calc = saldo_inicial + creditos - debitos
    saldo_final_visto = float(df["saldo"].iloc[-1]) if saldo_final_pdf is None else float(saldo_final_pdf)
    diferencia = saldo_final_calc - saldo_final_visto
    cuadra = abs(diferencia) < 0.01

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Saldo inicial", f"$ {fmt_ar(saldo_inicial)}")
    with c2: st.metric("Total créditos (+)", f"$ {fmt_ar(creditos)}")
    with c3: st.metric("Total débitos (−)", f"$ {fmt_ar(debitos)}")
    with c4: st.metric("Saldo final (PDF/tabla)", f"$ {fmt_ar(saldo_final_visto)}")
    with c5: st.metric("Saldo final calculado", f"$ {fmt_ar(saldo_final_calc)}")

    if cuadra:
        st.success("Conciliado.")
    else:
        st.error("No cuadra la conciliación.")

    # Derivados básicos para tabla
    df_out = df.copy()
    df_out["debito"]  = np.where(df_out["monto_pdf"] < 0, -df_out["monto_pdf"], 0.0)
    df_out["credito"] = np.where(df_out["monto_pdf"] > 0,  df_out["monto_pdf"], 0.0)
    df_out = df_out[["fecha", "descripcion", "debito", "credito", "monto_pdf", "saldo"]]
    st.caption("Detalle de movimientos")
    st.dataframe(
        df_out.style.format(
            {"debito": fmt_ar, "credito": fmt_ar, "monto_pdf": fmt_ar, "saldo": fmt_ar}
        ),
        use_container_width=True
    )

    return {
        "saldo_inicial": saldo_inicial,
        "creditos": creditos,
        "debitos": debitos,
        "saldo_final_pdf": saldo_final_visto,
        "saldo_final_calc": saldo_final_calc,
        "diferencia": diferencia,
        "df": df_out,
    }

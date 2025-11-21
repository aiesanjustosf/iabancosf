# ============================================================
# IA Resumen Bancario – Banco de Santa Fe (EXCLUSIVO)
# Parser unificado para CONSOLIDADO y DETALLADO
# AIE San Justo
# ============================================================

import io, re
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import pdfplumber

# --- UI / assets ---
HERE = Path(__file__).parent
ASSETS = HERE / "assets"
LOGO = ASSETS / "logo_aie.png"
FAVICON = ASSETS / "favicon-aie.ico"

st.set_page_config(
    page_title="IA Resumen Bancario – Banco de Santa Fe",
    page_icon=str(FAVICON) if FAVICON.exists() else None
)
if LOGO.exists():
    st.image(str(LOGO), width=200)
st.title("IA Resumen Bancario – Banco de Santa Fe")

# ============================================================
# REGEX BASE
# ============================================================

DATE_RE  = re.compile(r"\b\d{1,2}/\d{2}/\d{4}\b")
MONEY_RE = re.compile(r'(?<!\S)(?:-?\d{1,3}(?:\.\d{3})*|\d+),\d{2}(?!\S)')
LONG_INT_RE = re.compile(r"\b\d{6,}\b")

# ============================================================
# NORMALIZACIONES
# ============================================================

def normalize_money(tok: str) -> float:
    if not tok:
        return np.nan
    tok = tok.replace("−", "-")
    neg = tok.startswith("-")
    tok = tok.strip("-")
    if "," not in tok:
        return np.nan
    main, frac = tok.rsplit(",", 1)
    main = main.replace(".", "").replace(" ", "")
    try:
        val = float(f"{main}.{frac}")
        return -val if neg else val
    except:
        return np.nan

def fmt_ar(n):
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return "—"
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalize_desc(desc: str) -> str:
    if not desc:
        return ""
    u = desc.upper()
    for pref in ("SAN JUS ", "CASA RO ", "CENTRAL ", "GOBERNA ", "SANTA FE ", "ROSARIO "):
        if u.startswith(pref):
            u = u[len(pref):]
            break
    u = LONG_INT_RE.sub("", u)
    return " ".join(u.split())

# ============================================================
# IDENTIFICACIÓN DEL FORMATO
# ============================================================

def detect_format(lines):
    """
    Devuelve:
    - "consolidado"
    - "detallado"
    """

    text = "\n".join(lines).upper()

    if "FECHA MOVIMIENTO" in text and "CONCEPTO" in text:
        return "consolidado"

    if "MOVIMIENTOS DETALLADO" in text or "ORIGEN" in text:
        return "detallado"

    # fallback: si tiene columnas debito/credito pero no FECHA MOVIMIENTO
    deb_col = sum(1 for l in lines if re.search(r'\bD[ÉE]BITO\b', l.upper()))
    if deb_col > 1:
        return "consolidado"

    # fallback final
    return "consolidado"
# ============================================================
# PARSER SANTA FE – CONSOLIDADO
# ============================================================

def parse_consolidado(lines):
    """
    Lee PDF tipo 'Consolidado de cuentas'.
    Estructura:
    FECHA | CONCEPTO | DEBITO | CREDITO | SALDO
    """
    rows = []
    for ln in lines:
        ln_clean = " ".join(ln.split())
        m_date = DATE_RE.search(ln_clean)
        if not m_date:
            continue

        fecha = pd.to_datetime(m_date.group(0), dayfirst=True, errors="coerce")
        if pd.isna(fecha):
            continue

        # Todos los montos
        am = MONEY_RE.findall(ln_clean)
        if not am:
            continue

        desc_part = ln_clean[m_date.end():]
        parts = desc_part.split()

        # Detectar SALDO FINAL / SALDO ANTERIOR dentro de líneas
        u = ln_clean.upper()
        if "SALDO ANTERIOR" in u:
            # monto único
            saldo = normalize_money(am[-1])
            rows.append({
                "fecha": fecha,
                "descripcion": "SALDO ANTERIOR",
                "desc_norm": "SALDO ANTERIOR",
                "debito": 0.0,
                "credito": 0.0,
                "saldo": saldo,
            })
            continue

        # En CONSOLIDADO:
        # am[-1] = saldo
        saldo = normalize_money(am[-1])

        # Los dos anteriores pueden ser débito y crédito
        deb = cre = 0.0
        if len(am) >= 3:
            deb = normalize_money(am[-3])
            cre = normalize_money(am[-2])
        elif len(am) == 2:
            # A veces solo hay débito o solo crédito
            if "--" in desc_part:
                # por seguridad
                deb = cre = 0.0
            else:
                # si el número está antes del saldo y es positivo → crédito; si negativo → débito
                val = normalize_money(am[0])
                if val >= 0:
                    cre = val
                else:
                    deb = -val

        desc = normalize_desc(desc_part)

        rows.append({
            "fecha": fecha,
            "descripcion": desc,
            "desc_norm": desc,
            "debito": deb,
            "credito": cre,
            "saldo": saldo,
        })

    return pd.DataFrame(rows)

# ============================================================
# PARSER SANTA FE – DETALLADO
# ============================================================

def parse_detallado(lines):
    """
    Formato DETALLADO:
    FECHA | ORIGEN | CONCEPTO | DEBITO | CREDITO | SALDO?
    A veces NO trae saldo en cada línea. (pero SIEMPRE trae débito o crédito)
    """
    rows = []
    for ln in lines:
        ln_clean = " ".join(ln.split())
        m_date = DATE_RE.search(ln_clean)
        if not m_date:
            continue

        fecha = pd.to_datetime(m_date.group(0), dayfirst=True, errors="coerce")
        if pd.isna(fecha):
            continue

        tail = ln_clean[m_date.end():].strip()

        # Extraer montos
        am = MONEY_RE.findall(ln_clean)

        deb = cre = saldo = 0.0

        if len(am) == 1:
            # podría ser débito o crédito único, o saldo aislado
            value = normalize_money(am[0])
            # detectar si aparece en la parte final (saldo)
            if ln_clean.rstrip().endswith(am[0]):
                saldo = value
            else:
                # si es positivo → crédito, si negativo → débito
                if value >= 0:
                    cre = value
                else:
                    deb = -value

        elif len(am) == 2:
            # 2 montos: usualmente débito/crédito + saldo o débito + crédito
            first = normalize_money(am[0])
            second = normalize_money(am[1])

            if ln_clean.endswith(am[1]):
                saldo = second
                # entonces el primero es el movimiento
                if first >= 0:
                    cre = first
                else:
                    deb = -first
            else:
                # caso raro: dos movimientos
                if first >= 0:
                    cre = first
                else:
                    deb = -first
                if second >= 0:
                    cre += second
                else:
                    deb += -second

        elif len(am) >= 3:
            # típico: deb, cre, saldo
            deb = normalize_money(am[-3])
            cre = normalize_money(am[-2])
            saldo = normalize_money(am[-1])

        desc = normalize_desc(tail)

        rows.append({
            "fecha": fecha,
            "descripcion": desc,
            "desc_norm": desc,
            "debito": deb,
            "credito": cre,
            "saldo": saldo,
        })

    return pd.DataFrame(rows)

# ============================================================
# SALDO ANTERIOR / SALDO ÚLTIMO RESUMEN
# ============================================================

def find_saldo_anterior(lines):
    for ln in lines:
        u = ln.upper()
        am = MONEY_RE.findall(ln)
        if "SALDO ANTERIOR" in u and am:
            return normalize_money(am[-1])
        if "SALDO ULTIMO RESUMEN" in u and am:
            return normalize_money(am[-1])
        if "SALDO ÚLTIMO RESUMEN" in u and am:
            return normalize_money(am[-1])
    return np.nan
# ============================================================
# CLASIFICACIÓN DE MOVIMIENTOS
# ============================================================

def clasificar(desc, deb, cre):
    u = desc.upper()

    # SALDOS
    if "SALDO ANTERIOR" in u:
        return "Saldo Anterior"

    # LEY 25413 / IMPTRANS
    if "LEY 25413" in u or "IMPTRANS" in u or "IMP. LEY 25413" in u:
        return "Ley 25.413"

    # SIRCREB
    if "SIRCREB" in u:
        return "SIRCREB"

    # IVA 21%
    if "IVA GRAL" in u:
        return "IVA 21% (sobre comisiones)"

    # IVA 10.5%
    if "IVA RINS" in u or "IVA REDUC" in u:
        return "IVA 10,5% (sobre comisiones)"

    # Percepciones IVA
    if "IVA PERC" in u or "PERCEP" in u or "RG3337" in u or "RG 2408" in u:
        return "Percepciones de IVA"

    # Comisiones
    if "COMISION" in u or "COM." in u or "COMPENS" in u or "MANTENIMIENTO" in u:
        return "Gastos por comisiones"

    # Débitos automáticos / seguros
    if "SEG" in u or "SEGURO" in u or "DEB.AUT" in u:
        return "Débito automático"

    # Depósitos
    if "DEPOSITO" in u or "DEP.EFECTIVO" in u or "CR-DEPEF" in u:
        return "Depósito en Efectivo"

    # Transferencias
    if "TRANSF" in u or "TRSFE" in u:
        if cre > 0:
            return "Transferencia recibida"
        if deb > 0:
            return "Transferencia realizada"

    # Plazo fijo
    if "PLAZO FIJO" in u or "P.FIJO" in u or "P FIJO" in u:
        return "Plazo Fijo"

    # Cámara compensadora
    if "CALCHQ" in u or "CCSA" in u:
        return "Cámara compensadora"

    # Cheques
    if "CH" in u:
        return "Cheques"

    # Si nada coincide → usar signo
    if cre > 0:
        return "Crédito"
    if deb > 0:
        return "Débito"

    return "Otros"


# ============================================================
# FUNCIÓN PRINCIPAL PARA ARMAR EL DATAFRAME UNIFICADO
# ============================================================

def build_dataframe(file_bytes):
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        lines = []
        for p in pdf.pages:
            txt = p.extract_text() or ""
            for ln in txt.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)

    formato = detect_format(lines)

    if formato == "consolidado":
        df = parse_consolidado(lines)
    else:
        df = parse_detallado(lines)

    if df.empty:
        return df, formato, np.nan

    # Orden
    df = df.sort_values("fecha").reset_index(drop=True)

    # SALDO ANTERIOR explícito
    saldo_ant = find_saldo_anterior(lines)
    if not np.isnan(saldo_ant):
        df.loc[0, "saldo"] = saldo_ant

    # Clasificación
    df["Clasificación"] = df.apply(
        lambda r: clasificar(r["desc_norm"], r["debito"], r["credito"]),
        axis=1
    )

    return df, formato, saldo_ant


# ============================================================
# UI PRINCIPAL
# ============================================================

uploaded = st.file_uploader("Subí un PDF del Banco de Santa Fe", type=["pdf"])

if uploaded is None:
    st.info("La app no almacena datos. Subí un archivo para continuar.")
    st.stop()

data = uploaded.read()

df, formato, saldo_ant = build_dataframe(data)

if df.empty:
    st.error("No se detectaron movimientos en el PDF.")
    st.stop()

st.success(f"Formato detectado: **{formato.upper()}**")

# ============================================================
# CONCILIACIÓN
# ============================================================

df_sorted = df.copy().reset_index(drop=True)

saldo_inicial = df_sorted["saldo"].dropna().iloc[0] if not df_sorted["saldo"].dropna().empty else 0.0
total_debitos = df_sorted["debito"].sum()
total_creditos = df_sorted["credito"].sum()

# El saldo final se toma del último saldo real disponible
if df_sorted["saldo"].dropna().empty:
    saldo_final_pdf = saldo_inicial + total_creditos - total_debitos
else:
    saldo_final_pdf = df_sorted["saldo"].dropna().iloc[-1]

saldo_final_calc = saldo_inicial + total_creditos - total_debitos
dif = saldo_final_calc - saldo_final_pdf
cuadra = abs(dif) < 0.01

# ============================================================
# RESUMEN DEL PERÍODO
# ============================================================

st.subheader("Resumen del período")
c1, c2, c3 = st.columns(3)
c1.metric("Saldo inicial", f"$ {fmt_ar(saldo_inicial)}")
c2.metric("Créditos (+)", f"$ {fmt_ar(total_creditos)}")
c3.metric("Débitos (–)", f"$ {fmt_ar(total_debitos)}")

c4, c5, c6 = st.columns(3)
c4.metric("Saldo final (PDF)", f"$ {fmt_ar(saldo_final_pdf)}")
c5.metric("Saldo final calculado", f"$ {fmt_ar(saldo_final_calc)}")
c6.metric("Diferencia", f"$ {fmt_ar(dif)}")

if cuadra:
    st.success("Conciliado.")
else:
    st.error("No cuadra la conciliación.")

# ============================================================
# RESUMEN OPERATIVO (ARRIBA DE LA TABLA)
# ============================================================

st.subheader("Resumen Operativo: Registración Módulo IVA")

iva21   = df_sorted.loc[df_sorted["Clasificación"]=="IVA 21% (sobre comisiones)", "debito"].sum()
iva105  = df_sorted.loc[df_sorted["Clasificación"]=="IVA 10,5% (sobre comisiones)", "debito"].sum()
percep  = df_sorted.loc[df_sorted["Clasificación"]=="Percepciones de IVA", "debito"].sum()
ley25   = df_sorted.loc[df_sorted["Clasificación"]=="Ley 25.413", "debito"].sum()
sircreb = df_sorted.loc[df_sorted["Clasificación"]=="SIRCREB", "debito"].sum()

net21  = iva21  / 0.21 if iva21  else 0.0
net105 = iva105 / 0.105 if iva105 else 0.0

m1, m2, m3 = st.columns(3)
m1.metric("Neto 21%", f"$ {fmt_ar(net21)}")
m2.metric("IVA 21%",  f"$ {fmt_ar(iva21)}")
m3.metric("Bruto 21%", f"$ {fmt_ar(net21 + iva21)}")

n1, n2, n3 = st.columns(3)
n1.metric("Neto 10,5%", f"$ {fmt_ar(net105)}")
n2.metric("IVA 10,5%",  f"$ {fmt_ar(iva105)}")
n3.metric("Bruto 10,5%", f"$ {fmt_ar(net105 + iva105)}")

o1, o2, o3 = st.columns(3)
o1.metric("Percepciones IVA", f"$ {fmt_ar(percep)}")
o2.metric("Ley 25.413", f"$ {fmt_ar(ley25)}")
o3.metric("SIRCREB", f"$ {fmt_ar(sircreb)}")

# ============================================================
# TABLA DE MOVIMIENTOS
# ============================================================

st.subheader("Detalle de movimientos")
df_view = df_sorted.copy()

for c in ["debito", "credito", "saldo"]:
    df_view[c] = df_view[c].map(fmt_ar)

st.dataframe(df_view, use_container_width=True)

# ============================================================
# DESCARGAS
# ============================================================

st.subheader("Descargar")

try:
    import xlsxwriter
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_sorted.to_excel(writer, index=False, sheet_name="Movimientos")
        wb = writer.book
        ws = writer.sheets["Movimientos"]
        money_fmt = wb.add_format({"num_format": "#,##0.00"})
        date_fmt  = wb.add_format({"num_format": "dd/mm/yyyy"})

        for idx, col in enumerate(df_sorted.columns):
            ws.set_column(idx, idx, 18)

        for col in ["debito", "credito", "saldo"]:
            j = df_sorted.columns.get_loc(col)
            ws.set_column(j, j, 16, money_fmt)

        j = df_sorted.columns.get_loc("fecha")
        ws.set_column(j, j, 12, date_fmt)

    st.download_button(
        "📥 Descargar Excel",
        data=output.getvalue(),
        file_name="santafe_resumen.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

except:
    csv_bytes = df_sorted.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Descargar CSV (fallback)",
        data=csv_bytes,
        file_name="santafe_resumen.csv",
        mime="text/csv"
    )

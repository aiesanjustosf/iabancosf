# ia_resumen_bancario_santafe.py
# Herramienta para uso interno - AIE San Justo (Banco de Santa Fe)

import io, re
from pathlib import Path
import numpy as np, pandas as pd, streamlit as st

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
LOGO = ASSETS / "logo_aie.png"
FAVICON = ASSETS / "favicon-aie.ico"

st.set_page_config(
    page_title="IA Resumen Bancario – Banco de Santa Fe",
    page_icon=str(FAVICON) if FAVICON.exists() else None,
    layout="wide"
)

if LOGO.exists():
    st.image(str(LOGO), width=200)
st.title("IA Resumen Bancario – Banco de Santa Fe")

try:
    import pdfplumber
except Exception as e:
    st.error(f"No se pudo importar pdfplumber: {e}")
    st.stop()

DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
MONEY_RE = re.compile(r'(?<!\S)-?(?:\d{1,3}(?:\.\d{3})*|\d+)\s?,\s?\d{2}-?(?!\S)')
LONG_INT_RE = re.compile(r"\b\d{6,}\b")


def normalize_money(tok: str) -> float:
    if not tok:
        return np.nan
    tok = tok.strip().replace("−", "-")
    neg = tok.endswith("-") or tok.startswith("-")
    tok = tok.strip("-")
    if "," not in tok:
        return np.nan
    main, frac = tok.rsplit(",", 1)
    main = main.replace(".", "").replace(" ", "")
    try:
        val = float(f"{main}.{frac}")
        return -val if neg else val
    except Exception:
        return np.nan


def fmt_ar(n):
    return "—" if (n is None or (isinstance(n, float) and np.isnan(n))) else f"{n:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def lines_from_text(page):
    return [" ".join(l.split()) for l in (page.extract_text() or "").splitlines()]


def lines_from_words(page, ytol=2.0):
    words = page.extract_words(extra_attrs=["x0", "top"])
    if not words:
        return []
    words.sort(key=lambda w: (round(w["top"] / ytol), w["x0"]))
    lines, cur, band = [], [], None
    for w in words:
        b = round(w["top"] / ytol)
        if band is None or b == band:
            cur.append(w)
        else:
            lines.append(" ".join(x["text"] for x in cur))
            cur = [w]
        band = b
    if cur:
        lines.append(" ".join(x["text"] for x in cur))
    return [" ".join(l.split()) for l in lines]


def normalize_desc(desc):
    return " ".join(LONG_INT_RE.sub("", (desc or "").upper()).split())


def extract_all_lines(file_like):
    out = []
    with pdfplumber.open(file_like) as pdf:
        for pi, p in enumerate(pdf.pages, start=1):
            lt = lines_from_text(p)
            lw = lines_from_words(p, ytol=2.0)
            seen = set(lt)
            combined = lt + [l for l in lw if l not in seen]
            for l in combined:
                if l.strip():
                    out.append((pi, " ".join(l.split())))
    return out


def find_saldo_anterior(lines):
    for _, ln in lines:
        u = ln.upper()
        if "SALDO ANTERIOR" in u or "SALDO ULTIMO RESUMEN" in u:
            am = list(MONEY_RE.finditer(ln))
            if am:
                return normalize_money(am[-1].group(0))
    return np.nan


def find_saldo_final_pdf(lines):
    for _, ln in reversed(lines):
        u = ln.upper()
        if "SALDO AL" in u or "SALDO FINAL" in u:
            am = list(MONEY_RE.finditer(ln))
            if am:
                return normalize_money(am[-1].group(0))
    return np.nan


# ------------------------------------------------------------------
# DETECCIÓN DE SIGNO – BANCO SANTA FE (ajustada)
# ------------------------------------------------------------------
def detectar_signo_santafe(desc_norm: str) -> str:
    u = (desc_norm or "").upper()

    # Créditos claros (ingresos)
    credit_keywords = [
        "DTNPROVE",
        "DEP EFEC",
        "DEPOSITO EFECTIVO",
        "DEP CH PROPIO",
        "D CH PRO",
        "TRANLINK",            # transferencias
        "TRANSCRE",            # FIX: TRANSCRE ... CREDIN ... (venía quedando como débito)
        "CR-TRSFE",            # transferencias recibidas
        "TR.CTA",              # transferencias a / desde cuenta
        "CN-IMPTR",            # nota de crédito impuesto ley 25413
        "CNDBEMBA",            # nota de crédito embargos
        "TRANSACD",            # TRANSAC. DEBIN → Debin acreditado
    ]
    if any(k in u for k in credit_keywords):
        return "credito"

    # Débitos claros (egresos)
    debit_keywords = [
        "DB/PG",               # débitos por pagos
        "DB-SNP",              # débitos AFIP / seguros
        "DB-EMBAR",            # embargos
        "IMPTRANS",            # Impuesto Ley 25.413
        "COMMANTP",            # comisiones mantenimiento
        "COMRESUM",            # comisiones extracto
        "DEBITO INMEDIATO",    # otros débitos automáticos
    ]
    if any(k in u for k in debit_keywords):
        return "debito"

    # Fallbacks por prefijo del concepto
    if u.startswith("CR-") or " CR-" in u:
        return "credito"
    if u.startswith("DB-") or " DB-" in u:
        return "debito"

    # Por defecto, asumimos débito
    return "debito"


# ------------------------------------------------------------------
# CLASIFICACIÓN PARA RESUMEN OPERATIVO (ajustada IVA PERC)
# ------------------------------------------------------------------
def clasificar(desc, desc_norm, deb, cre):
    u = (desc or "").upper()

    # Percepciones de IVA del resumen (ej: IVA PERC / IVA PERCEP.RG3337)
    if "IVA PERC" in u or "IVA PERCEP" in u or "PERCEP.RG" in u:
        return "Percepciones de IVA"

    if "IVA GRAL" in u:
        return "IVA 21% (sobre comisiones)"
    if "IVA RINS" in u:
        return "IVA 10,5% (sobre comisiones)"
    if "IMPTRANS" in u or "LEY 25413" in u:
        return "LEY 25.413"
    if "SIRCREB" in u:
        return "SIRCREB"
    if "COM" in u:
        return "Gastos por comisiones"
    if "DEBITO INMEDIATO" in u:
        return "Débito automático"

    if cre:
        return "Crédito"
    if deb:
        return "Débito"
    return "Otros"


# ------------------------------------------------------------------
# DETECCIÓN / CLASIFICACIÓN DE PRÉSTAMOS (listado de “créditos”)
# ------------------------------------------------------------------
def clasificar_prestamo(desc_norm: str, debito: float, credito: float) -> str:
    """
    Devuelve:
      - "" si no parece préstamo/crédito
      - "Acreditación préstamo"
      - "Pago cuota préstamo"
      - "Débito préstamo"
      - "Crédito préstamo"
      - "Ajuste/Reverso préstamo"
    """
    u = (desc_norm or "").upper()

    # Señales “fuertes” (incluye CREDIN porque suele venir asociado a créditos)
    es_prestamo = (
        ("PREST" in u) or
        ("PRST" in u) or
        ("CREDIN" in u) or
        (("CREDITO" in u) and any(k in u for k in ["CUOTA", "PERSONAL", "HIPOT", "PREAP", "PREST"]))
    )
    if not es_prestamo:
        return ""

    # Ajustes/reversos
    if any(k in u for k in ["REVERS", "ANUL", "AJUST"]):
        return "Ajuste/Reverso préstamo"

    if debito > 0:
        if any(k in u for k in ["CUOTA", "PAGO", "AMORT", "CANCEL"]):
            return "Pago cuota préstamo"
        return "Débito préstamo"

    if credito > 0:
        # si hubiese reintegro, quedaría arriba por revers/ajust
        return "Acreditación préstamo"

    return "Crédito/Préstamo (sin importe)"


def parse_movimientos_santafe(lines):
    rows = []
    orden = 0
    for pageno, ln in lines:
        u = ln.upper()
        if "FECHA MOVIMIENTO" in u or "CONCEPTO" in u:
            continue
        if "SALDO ANTERIOR" in u or "SALDO ULTIMO RESUMEN" in u:
            continue

        d = DATE_RE.search(ln)
        if not d:
            continue

        am = list(MONEY_RE.finditer(ln))
        if not am:
            continue

        mcount = len(am)
        if mcount >= 2:
            importe_str = am[-2].group(0)
            saldo_str = am[-1].group(0)
            saldo_pdf = normalize_money(saldo_str)
        else:
            importe_str = am[-1].group(0)
            saldo_pdf = np.nan

        importe = normalize_money(importe_str)
        first_money = am[0]
        desc = ln[d.end():first_money.start()].strip()

        orden += 1
        rows.append({
            "fecha": pd.to_datetime(d.group(0), dayfirst=True, errors="coerce"),
            "descripcion": desc,
            "desc_norm": normalize_desc(desc),
            "importe_raw": abs(importe),
            "saldo_pdf": saldo_pdf,
            "mcount": mcount,
            "pagina": pageno,
            "orden": orden
        })
    return pd.DataFrame(rows)


uploaded = st.file_uploader("Subí un PDF del resumen bancario (Banco de Santa Fe)", type=["pdf"])
if uploaded is None:
    st.stop()

data = uploaded.read()
lines = extract_all_lines(io.BytesIO(data))
df_raw = parse_movimientos_santafe(lines)

tiene_saldo_por_linea = df_raw["mcount"].max() >= 2
saldo_anterior = find_saldo_anterior(lines)
saldo_final_pdf = find_saldo_final_pdf(lines)

df = df_raw.sort_values(["fecha", "pagina", "orden"]).reset_index(drop=True)

# Insertar saldo anterior
if not np.isnan(saldo_anterior):
    apertura = {
        "fecha": df["fecha"].min() - pd.Timedelta(days=1),
        "descripcion": "SALDO ANTERIOR",
        "desc_norm": "SALDO ANTERIOR",
        "importe_raw": 0.0,
        "saldo_pdf": saldo_anterior,
        "mcount": 0,
        "pagina": 0,
        "orden": 0
    }
    df = pd.concat([pd.DataFrame([apertura]), df], ignore_index=True)

df["debito"] = 0.0
df["credito"] = 0.0
df["saldo"] = np.nan
df["signo"] = ""

# ---------- Caso 1: PDF con SALDO por línea ----------
if tiene_saldo_por_linea:
    for idx, row in df.iterrows():
        if row["desc_norm"] == "SALDO ANTERIOR":
            continue
        importe = float(row["importe_raw"])
        signo = detectar_signo_santafe(row["desc_norm"])
        if signo == "debito":
            df.at[idx, "debito"] = importe
        else:
            df.at[idx, "credito"] = importe

    df["saldo"] = saldo_anterior + df["credito"].cumsum() - df["debito"].cumsum()
    df.loc[df["debito"] > 0, "signo"] = "debito"
    df.loc[df["credito"] > 0, "signo"] = "credito"

# ---------- Caso 2: PDF SIN saldo por línea ----------
else:
    saldos, debitos, creditos, signos = [], [], [], []
    saldo = float(saldo_anterior) if not np.isnan(saldo_anterior) else 0.0
    for idx, row in df.iterrows():
        if idx == 0 and row["desc_norm"] == "SALDO ANTERIOR":
            saldos.append(saldo)
            debitos.append(0.0)
            creditos.append(0.0)
            signos.append("saldo")
            continue

        importe = float(row["importe_raw"])
        signo = detectar_signo_santafe(row["desc_norm"])
        if signo == "debito":
            saldo -= importe
            deb, cre = importe, 0.0
        else:
            saldo += importe
            deb, cre = 0.0, importe

        saldos.append(saldo)
        debitos.append(deb)
        creditos.append(cre)
        signos.append(signo)

    df["saldo"] = saldos
    df["debito"] = debitos
    df["credito"] = creditos
    df["signo"] = signos

# Excluir saldo final como movimiento
df = df[~df["desc_norm"].str.upper().str.contains("SALDO AL|SALDO FINAL", na=False)]
df = df[~((df["desc_norm"] == "") & (df["debito"] > 0) & (df["orden"] > df["orden"].max() - 2))]

# Clasificación
df["Clasificación"] = df.apply(
    lambda r: clasificar(
        str(r.get("descripcion", "")),
        str(r.get("desc_norm", "")),
        float(r.get("debito", 0.0)),
        float(r.get("credito", 0.0))
    ),
    axis=1
)

# ===========================
#   RESUMEN / CONCILIACIÓN
# ===========================
df_sorted = df.reset_index(drop=True)

saldo_inicial = float(df_sorted["saldo"].iloc[0])
total_debitos = float(df_sorted["debito"].sum())
total_creditos = float(df_sorted["credito"].sum())

saldo_final_visto = float(saldo_final_pdf) if not np.isnan(saldo_final_pdf) else float(df_sorted["saldo"].iloc[-1])
saldo_final_calculado = saldo_inicial + total_creditos - total_debitos
diferencia = saldo_final_calculado - saldo_final_visto
cuadra = abs(diferencia) < 0.01

st.subheader("Resumen del período")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Saldo inicial", f"$ {fmt_ar(saldo_inicial)}")
with c2:
    st.metric("Créditos (+)", f"$ {fmt_ar(total_creditos)}")
with c3:
    st.metric("Débitos (–)", f"$ {fmt_ar(total_debitos)}")

c4, c5, c6 = st.columns(3)
with c4:
    st.metric("Saldo final (PDF)", f"$ {fmt_ar(saldo_final_visto)}")
with c5:
    st.metric("Saldo final calculado", f"$ {fmt_ar(saldo_final_calculado)}")
with c6:
    st.metric("Diferencia", f"$ {fmt_ar(diferencia)}")

if cuadra:
    st.success("Conciliado.")
else:
    st.error("No cuadra la conciliación (revisar signos/clasificación).")

st.markdown("---")

# ===========================
#   RESUMEN OPERATIVO
# ===========================
st.subheader("Resumen Operativo: Registración Módulo IVA")

iva21 = float(df_sorted.loc[df_sorted["Clasificación"].eq("IVA 21% (sobre comisiones)"), "debito"].sum())
iva105 = float(df_sorted.loc[df_sorted["Clasificación"].eq("IVA 10,5% (sobre comisiones)"), "debito"].sum())
net21 = round(iva21 / 0.21, 2) if iva21 else 0.0
net105 = round(iva105 / 0.105, 2) if iva105 else 0.0

percep_iva = float(df_sorted.loc[df_sorted["Clasificación"].eq("Percepciones de IVA"), "debito"].sum())
ley_25413 = float(df_sorted.loc[df_sorted["Clasificación"].eq("LEY 25.413"), "debito"].sum())
sircreb = float(df_sorted.loc[df_sorted["Clasificación"].eq("SIRCREB"), "debito"].sum())

# Total gastos bancarios
gastos_mask = df_sorted["Clasificación"].isin([
    "IVA 21% (sobre comisiones)",
    "IVA 10,5% (sobre comisiones)",
    "LEY 25.413",
    "SIRCREB",
    "Gastos por comisiones",
    "Débito automático"
])
total_gastos = float(df_sorted.loc[gastos_mask, "debito"].sum())

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Neto Comisiones 21%", f"$ {fmt_ar(net21)}")
with m2:
    st.metric("IVA 21%", f"$ {fmt_ar(iva21)}")
with m3:
    st.metric("Bruto 21%", f"$ {fmt_ar(net21 + iva21)}")

n1, n2, n3 = st.columns(3)
with n1:
    st.metric("Neto Comisiones 10,5%", f"$ {fmt_ar(net105)}")
with n2:
    st.metric("IVA 10,5%", f"$ {fmt_ar(iva105)}")
with n3:
    st.metric("Bruto 10,5%", f"$ {fmt_ar(net105 + iva105)}")

o1, o2, o3 = st.columns(3)
with o1:
    st.metric("Percepciones de IVA", f"$ {fmt_ar(percep_iva)}")
with o2:
    st.metric("Ley 25.413", f"$ {fmt_ar(ley_25413)}")
with o3:
    st.metric("SIRCREB", f"$ {fmt_ar(sircreb)}")

st.metric("Total Gastos Bancarios", f"$ {fmt_ar(total_gastos)}")

st.markdown("---")

# ===========================
#   PRÉSTAMOS / CRÉDITOS (LISTADO)
# ===========================
st.subheader("Préstamos / Créditos detectados (acreditaciones, cuotas, etc.)")

df_sorted["Evento préstamo"] = df_sorted.apply(
    lambda r: clasificar_prestamo(
        str(r.get("desc_norm", "")),
        float(r.get("debito", 0.0)),
        float(r.get("credito", 0.0))
    ),
    axis=1
)

df_prest = df_sorted[df_sorted["Evento préstamo"].ne("")].copy()

if df_prest.empty:
    st.info("No se detectaron movimientos de préstamos/créditos en este período (según reglas actuales).")
else:
    # Métricas rápidas
    total_acreditaciones = float(df_prest.loc[df_prest["Evento préstamo"].eq("Acreditación préstamo"), "credito"].sum())
    total_cuotas = float(df_prest.loc[df_prest["Evento préstamo"].eq("Pago cuota préstamo"), "debito"].sum())
    total_debitos_prest = float(df_prest["debito"].sum())
    total_creditos_prest = float(df_prest["credito"].sum())
    neto_prest = total_creditos_prest - total_debitos_prest

    p1, p2, p3, p4 = st.columns(4)
    with p1:
        st.metric("Acreditaciones (prést.)", f"$ {fmt_ar(total_acreditaciones)}")
    with p2:
        st.metric("Cuotas pagadas (prést.)", f"$ {fmt_ar(total_cuotas)}")
    with p3:
        st.metric("Débitos totales (prést.)", f"$ {fmt_ar(total_debitos_prest)}")
    with p4:
        st.metric("Neto (cr - db)", f"$ {fmt_ar(neto_prest)}")

    df_prest_view = df_prest[["fecha", "descripcion", "Evento préstamo", "debito", "credito", "saldo"]].copy()
    for c in ("debito", "credito", "saldo"):
        df_prest_view[c] = df_prest_view[c].map(fmt_ar)
    st.dataframe(df_prest_view, use_container_width=True)

    # Descarga específica préstamos (Excel con fallback CSV)
    st.markdown("**Descarga del listado de préstamos/créditos**")
    try:
        import xlsxwriter
        out_p = io.BytesIO()
        with pd.ExcelWriter(out_p, engine="xlsxwriter") as writer:
            df_prest.to_excel(writer, index=False, sheet_name="Prestamos")
            wb = writer.book
            ws = writer.sheets["Prestamos"]
            money_fmt = wb.add_format({"num_format": "#,##0.00"})
            date_fmt = wb.add_format({"num_format": "dd/mm/yyyy"})

            for idx, col in enumerate(df_prest.columns, start=0):
                col_values = df_prest[col].astype(str)
                max_len = max(len(col), *(len(v) for v in col_values))
                ws.set_column(idx, idx, min(max_len + 2, 45))

            for c in ["debito", "credito", "saldo", "importe_raw", "saldo_pdf"]:
                if c in df_prest.columns:
                    j = df_prest.columns.get_loc(c)
                    ws.set_column(j, j, 16, money_fmt)
            if "fecha" in df_prest.columns:
                j = df_prest.columns.get_loc("fecha")
                ws.set_column(j, j, 14, date_fmt)

        st.download_button(
            "📥 Descargar préstamos (Excel)",
            data=out_p.getvalue(),
            file_name="prestamos_santafe.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except Exception:
        csv_p = df_prest.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Descargar préstamos (CSV)",
            data=csv_p,
            file_name="prestamos_santafe.csv",
            mime="text/csv",
            use_container_width=True
        )

st.markdown("---")

# ===========================
#   DETALLE DE MOVIMIENTOS
# ===========================
st.subheader("Detalle de movimientos")
df_view = df_sorted.copy()
for c in ("debito", "credito", "saldo"):
    df_view[c] = df_view[c].map(fmt_ar)
st.dataframe(df_view, use_container_width=True)

# ===========================
#   DESCARGAS
# ===========================
st.subheader("Descargar")
try:
    import xlsxwriter
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_sorted.to_excel(writer, index=False, sheet_name="Movimientos")

        # Hoja extra (si hay préstamos detectados)
        if not df_prest.empty:
            df_prest.to_excel(writer, index=False, sheet_name="Prestamos")

        wb = writer.book
        ws = writer.sheets["Movimientos"]
        money_fmt = wb.add_format({"num_format": "#,##0.00"})
        date_fmt = wb.add_format({"num_format": "dd/mm/yyyy"})

        for idx, col in enumerate(df_sorted.columns, start=0):
            col_values = df_sorted[col].astype(str)
            max_len = max(len(col), *(len(v) for v in col_values))
            ws.set_column(idx, idx, min(max_len + 2, 40))

        for c in ["debito", "credito", "saldo"]:
            if c in df_sorted.columns:
                j = df_sorted.columns.get_loc(c)
                ws.set_column(j, j, 16, money_fmt)

        if "fecha" in df_sorted.columns:
            j = df_sorted.columns.get_loc("fecha")
            ws.set_column(j, j, 14, date_fmt)

    st.download_button(
        "📥 Descargar Excel",
        data=output.getvalue(),
        file_name="resumen_bancario_santafe.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
except Exception:
    csv_bytes = df_sorted.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Descargar CSV (fallback)",
        data=csv_bytes,
        file_name="resumen_bancario_santafe.csv",
        mime="text/csv",
        use_container_width=True
    )

# ===========================
#   PDF DEL RESUMEN OPERATIVO
# ===========================
st.subheader("Descargar PDF del Resumen Operativo")
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        leftMargin=40, rightMargin=40,
        topMargin=40, bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        alignment=1,
        spaceAfter=12
    )
    subtitle_style = ParagraphStyle(
        "Subtitulo",
        parent=styles["Heading2"],
        alignment=1,
        fontSize=12,
        spaceAfter=12
    )
    normal = styles["Normal"]

    story = []

    # Logo (si existe)
    try:
        if LOGO.exists():
            logo_img = Image(str(LOGO), width=120, height=40)
            logo_img.hAlign = "RIGHT"
            story.append(logo_img)
            story.append(Spacer(1, 10))
    except Exception:
        pass

    story.append(Paragraph("Resumen Operativo – Banco de Santa Fe", title_style))
    story.append(Paragraph("Registración Módulo IVA", subtitle_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Resumen del período</b>", normal))
    story.append(Spacer(1, 6))

    tabla_resumen_data = [
        ["Concepto", "Importe"],
        ["Saldo inicial", f"$ {fmt_ar(saldo_inicial)}"],
        ["Créditos (+)", f"$ {fmt_ar(total_creditos)}"],
        ["Débitos (–)", f"$ {fmt_ar(total_debitos)}"],
        ["Saldo final calculado", f"$ {fmt_ar(saldo_final_calculado)}"],
        ["Saldo final (según PDF)", f"$ {fmt_ar(saldo_final_visto)}"],
        ["Diferencia", f"$ {fmt_ar(diferencia)}"],
    ]

    tabla_resumen = Table(tabla_resumen_data, colWidths=[220, 120])
    tabla_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(tabla_resumen)
    story.append(Spacer(1, 16))

    story.append(Paragraph("<b>Detalle para Módulo IVA</b>", normal))
    story.append(Spacer(1, 6))

    tabla_iva_data = [
        ["Concepto", "Neto", "IVA", "Total"],
        ["Comisiones 21%", f"$ {fmt_ar(net21)}", f"$ {fmt_ar(iva21)}", f"$ {fmt_ar(net21 + iva21)}"],
        ["Comisiones 10,5%", f"$ {fmt_ar(net105)}", f"$ {fmt_ar(iva105)}", f"$ {fmt_ar(net105 + iva105)}"],
        ["Percepciones de IVA", "", f"$ {fmt_ar(percep_iva)}", f"$ {fmt_ar(percep_iva)}"],
        ["Ley 25.413", "", f"$ {fmt_ar(ley_25413)}", f"$ {fmt_ar(ley_25413)}"],
        ["SIRCREB", "", f"$ {fmt_ar(sircreb)}", f"$ {fmt_ar(sircreb)}"],
    ]

    tabla_iva = Table(tabla_iva_data, colWidths=[200, 80, 80, 80])
    tabla_iva.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(tabla_iva)
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"<b>Total gastos bancarios imputables a resultados:</b> $ {fmt_ar(total_gastos)}",
        normal
    ))

    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Informe generado con IA Resumen Bancario – AIE San Justo. Uso interno exclusivamente.",
        ParagraphStyle("Pie", parent=normal, fontSize=8, textColor=colors.grey)
    ))

    doc.build(story)
    pdf_bytes = pdf_buffer.getvalue()

    st.download_button(
        "📥 Descargar PDF",
        data=pdf_bytes,
        file_name="resumen_operativo_santafe.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
except Exception as e:
    st.error(f"No se pudo generar el PDF: {e}")

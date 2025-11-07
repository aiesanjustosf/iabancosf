
import io
import pdfplumber
import streamlit as st
import pandas as pd

from parsers.dispatch import detect_bank, run_parser_for

st.set_page_config(page_title="IA Bancos Gestión", page_icon=":bar_chart:", layout="wide")

col_logo, col_title = st.columns([1,6])
with col_logo:
    st.image("assets/logo_aie.png", use_column_width=True)
with col_title:
    st.title("IA Bancos Gestión")

st.caption("Prueba con dispatcher por banco + parsers separados.")

up = st.file_uploader("Subí un PDF bancario", type=["pdf"])

force = st.selectbox("Forzar identificación (opcional)", ["Auto (detectar)", "Banco Galicia", "Banco de la Nación Argentina", "Banco de Santa Fe", "Banco Macro", "Banco Santander"])

if up is not None:
    try:
        data = up.read()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
        st.success(f"PDF abierto OK. Páginas: {len(pages_text)}")
    except Exception as e:
        st.error(f"No pude abrir el PDF: {e}")
        st.stop()

    all_text = "\n".join(pages_text)
    if force != "Auto (detectar)":
        if "Galicia" in force:
            slug = "galicia"
        elif "Nación" in force:
            slug = "nacion"
        elif "Santa Fe" in force:
            slug = "santafe"
        elif "Macro" in force:
            slug = "macro"
        else:
            slug = "santander"
    else:
        slug = detect_bank(all_text)

    nombre_banco = {
        "galicia":"Banco Galicia",
        "nacion":"Banco de la Nación Argentina",
        "santafe":"Banco de Santa Fe",
        "macro":"Banco Macro",
        "santander":"Banco Santander",
        "desconocido":"Desconocido"
    }.get(slug, "Desconocido")

    st.info(f"Detectado: {nombre_banco}")

    resumen, df = run_parser_for(slug, pages_text)

    st.subheader(f"CUENTA ({nombre_banco}) · Parser {resumen['parser']}")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Saldo inicial", f"$ {resumen['saldo_inicial']:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    with c2: st.metric("Total créditos (+)", f"$ {resumen['total_creditos']:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    with c3: st.metric("Total débitos (−)", f"$ {resumen['total_debitos']:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    with c4: st.metric("Saldo final (PDF)", f"$ {resumen['saldo_pdf']:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

    ok = resumen["cuadra"]
    st.success("Conciliado.") if ok else st.error("No cuadra la conciliación.")
    st.caption(f"Saldo final calculado: $ {resumen['saldo_calc']:,.2f} — Diferencia: $ {resumen['diferencia']:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

    st.subheader("Detalle de movimientos")
    st.dataframe(df, use_container_width=True, height=360)

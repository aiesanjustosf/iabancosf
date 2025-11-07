
import re, pandas as pd
CURRENCY_RE = re.compile(r"[-]?\$?\s*([0-9\.\s]{1,}),([0-9]{2})")

def ar_to_float(s: str) -> float:
    if s is None:
        return 0.0
    t = str(s).replace("\xa0"," ").replace("\u2007"," ").strip()
    neg = "-" in t
    m = CURRENCY_RE.search(t)
    if not m:
        t2 = re.sub(r"[^\d\-]", "", t)
        try: return float(t2)
        except: return 0.0
    entero = m.group(1).replace(".","").replace(" ","")
    dec = m.group(2)
    try: val = float(f"{int(entero)}.{dec}")
    except: 
        try: val = float(f"{entero}.{dec}")
        except: val = 0.0
    return -val if neg else val

def show_resumen_periodo(saldo_ini, total_cred, total_deb, saldo_pdf):
    import streamlit as st
    col1,col2,col3,col4 = st.columns(4)
    f = lambda x: f"$ {x:,.2f}".replace(",","X").replace(".",",").replace("X",".")
    col1.metric("Saldo inicial", f(saldo_ini))
    col2.metric("Total créditos (+)", f(total_cred))
    col3.metric("Total débitos (−)", f(total_deb))
    col4.metric("Saldo final (PDF)", f(saldo_pdf))
    saldo_calc = saldo_ini + total_cred - total_deb
    diff = round(saldo_pdf - saldo_calc, 2)
    st.metric("Diferencia", f(diff))
    if abs(diff) < 0.01: st.success("Conciliado.")
    else: st.error("No cuadra la conciliación.")
    return diff

def render_movs(df):
    import streamlit as st
    if df is None or df.empty:
        st.info("Sin movimientos parseados (aún)."); return
    st.subheader("Detalle de movimientos")
    st.dataframe(df, use_container_width=True)

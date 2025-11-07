
import io, pdfplumber, re, pandas as pd, streamlit as st
from parsers.utils import ar_to_float, show_resumen_periodo, render_movs

def parse_galicia(pdf_bytes: bytes, full_text: str) -> None:
    st.header("Cuenta Corriente (Galicia) · Parser")

    movs, saldo_ini, saldo_pdf = [], 0.0, 0.0
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as p:
        for i, page in enumerate(p.pages):
            text = page.extract_text() or ""
            if i == 0:
                m = re.search(r"SALDO\s+INICIAL[^^$]*\$\s*([0-9\.\s]+,[0-9]{2})", text, re.IGNORECASE)
                if m: saldo_ini = ar_to_float(m.group(0))
            if i == len(p.pages)-1:
                m = re.search(r"SALDO\s+FINAL[^^$]*\$\s*([0-9\.\s]+,[0-9]{2})", text, re.IGNORECASE)
                if m: saldo_pdf = ar_to_float(m.group(0))
            for ln in (text or "").split("\n"):
                if re.search(r"[,][0-9]{2}", ln):
                    val = ar_to_float(ln); desc = re.sub(r"\s+"," ",ln).strip()[:80]
                    if "-" in ln: movs.append({"desc_norm":desc,"debito":abs(val),"credito":0.0})
                    else:         movs.append({"desc_norm":desc,"debito":0.0,"credito":abs(val)})
    df = pd.DataFrame(movs)
    total_deb = round(df["debito"].sum(),2) if not df.empty else 0.0
    total_cred= round(df["credito"].sum(),2) if not df.empty else 0.0
    show_resumen_periodo(saldo_ini,total_cred,total_deb,saldo_pdf)
    render_movs(df)


import streamlit as st
from parsers.parser_galicia import parse_galicia
from parsers.parser_generico import parse_generico

GALICIA = "Banco Galicia"
BNA     = "Banco de la Nación Argentina"
SANTAFE = "Banco de Santa Fe"
MACRO   = "Banco Macro"
SANTAND = "Banco Santander"

def detect_bank(full_text: str) -> str:
    t = (full_text or "").upper()
    if "BANCO GALICIA" in t or " GALICIA " in t:
        return GALICIA
    if "BANCO DE LA NACIÓN ARGENTINA" in t or "BANCO DE LA NACION ARGENTINA" in t or " BNA " in t:
        return BNA
    if "BANCO DE SANTA FE" in t:
        return SANTAFE
    if "BANCO MACRO" in t:
        return MACRO
    if "BANCO SANTANDER" in t or "SANTANDER RIO" in t or "SANTANDER RÍO" in t:
        return SANTAND
    return "Banco (no identificado)"

def run_parser(bank: str, pdf_bytes: bytes, full_text: str) -> None:
    if bank == GALICIA:
        parse_galicia(pdf_bytes, full_text)
    elif bank in {BNA, SANTAFE, MACRO, SANTAND}:
        parse_generico(bank, pdf_bytes, full_text)
    else:
        st.warning("No pude identificar el banco. Probá forzar la opción.")

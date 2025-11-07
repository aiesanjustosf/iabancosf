from . import common as C

def render(data: bytes, full_text: str):
    lines = C.extract_all_lines(data)
    df = C.parse_generic_table(lines)
    # Fallback Santa Fe: si el encabezado trae "SALDO ANTERIOR" en la tabla, el genérico igual concilia con la reconstrucción
    C.render_summary(df, titulo="CUENTA (Santa Fe) · Nro s/n")

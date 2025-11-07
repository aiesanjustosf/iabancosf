# IA Bancos Gestión

App de prueba con **dispatcher por banco** y parsers separados:
- `Banco Galicia` → parser dedicado (débito negativo a la izquierda).
- `Banco Nación`, `Banco Santa Fe`, `Banco Macro`, `Banco Santander` → parser genérico.

## Estructura
- `app.py` – UI Streamlit y ruteo.
- `parsers/dispatch.py` – detección y selección de parser.
- `parsers/parser_galicia.py` – reglas específicas de Galicia.
- `parsers/parser_generico.py` – reglas comunes para los otros bancos.
- `parsers/utils.py` – conversión AR, conciliación, heurísticas.
- `assets/logo_aie.png` – logo en cabecera.
- `requirements.txt`, `runtime.txt`

> Runtime fijado a **Python 3.12.0** para Streamlit Cloud.


import re
from .parser_galicia import parse_galicia
from .parser_generico import parse_generico

BANK_PATTERNS = {
    "galicia": re.compile(r"galicia", re.I),
    "nacion": re.compile(r"naci[oó]n", re.I),
    "santafe": re.compile(r"santa\s*fe", re.I),
    "macro": re.compile(r"macro", re.I),
    "santander": re.compile(r"santander", re.I),
}

def detect_bank(all_text: str) -> str:
    t = all_text.lower()
    for slug, pat in BANK_PATTERNS.items():
        if pat.search(t):
            return slug
    return "desconocido"

def run_parser_for(slug: str, pages_text: list[str]):
    if slug == "galicia":
        return parse_galicia(pages_text)
    # resto
    return parse_generico(pages_text)

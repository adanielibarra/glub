"""Language of the log messages and the report (English or Spanish).

The window sets it from the language chosen in the Home tab; the Processing tools
from the saved GLUB setting. L(en, es) picks the text. Kept tiny on purpose:
no QGIS imports, so the core stays testable.
"""
_lang = "en"


def set_lang(code):
    global _lang
    _lang = "es" if code == "es" else "en"


def lang():
    return _lang


def L(en, es):
    return es if _lang == "es" else en

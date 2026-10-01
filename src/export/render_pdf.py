##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## PDF export: the HTML page printed by WeasyPrint, optional (requirements-export.txt)
##
from export import render_html

EXTENSION: str = "pdf"

MISSING: str = ("L'export PDF a besoin de WeasyPrint : pip install -r requirements-export.txt "
                "(et Pango sur le système : https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)")

def render(document: dict) -> bytes:
    """ The document as a PDF: the page of the HTML export, laid out by its print styles (A4, light, all shown) """
    # Imported here: without the export extras, Louis never needs WeasyPrint (nor Pango) for anything else
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        raise ImportError(f"{MISSING} ({e})") from e
    return HTML(string=render_html.render(document)).write_pdf()

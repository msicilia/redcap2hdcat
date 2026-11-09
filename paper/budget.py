"""Estimate the printed length of main.tex under the Methods Print fee rule.

Thieme: the first 5 printed pages are free, about 22,000 characters including spaces;
deduct 1,500 characters for each figure or table; EUR 125 per page beyond 5.
Counts the text of the title, abstract, body, back matter, captions and the reference
list (from main.bbl), as plain text. Comments and LaTeX commands are stripped.

Usage: python budget.py   (after latexmk, so that main.bbl exists)
"""

import re
import sys
from pathlib import Path

CHARS_PER_PAGE = 22_000 / 5
FLOAT_COST = 1_500
FREE_PAGES = 5
EUR_PER_PAGE = 125

here = Path(__file__).parent


def plain(tex: str) -> str:
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    tex = re.sub(r"\\TBD\{", "{", tex)
    tex = re.sub(r"\\(begin|end)\{[^}]*\}(\[[^]]*\])?(\{[^}]*\})?", " ", tex)
    tex = re.sub(r"\\(cite[pt]?|ref|label|citep)\{[^}]*\}", "", tex)
    tex = re.sub(r"\\(newblock|bibitem\[[^]]*\]\{[^}]*\}|bibitem\{[^}]*\})", " ", tex)
    tex = re.sub(r"\\[a-zA-Z@]+\*?(\[[^]]*\])?", " ", tex)
    tex = re.sub(r"[{}$&~\\]", " ", tex)
    tex = re.sub(r"\s+", " ", tex)
    return tex.strip()


src = (here / "main.tex").read_text(encoding="utf-8")
body = src.split(r"\begin{document}", 1)[1]
body_chars = len(plain(body))
bbl = here / "main.bbl"
ref_chars = len(plain(bbl.read_text(encoding="utf-8"))) if bbl.exists() else 0
n_floats = len(re.findall(r"\\begin\{(table|figure)\}", src)) + len(
    re.findall(r"\\textbf\{Figure \d+\.\}", src)
)
effective = body_chars + ref_chars + FLOAT_COST * n_floats
pages = effective / CHARS_PER_PAGE
extra = max(0, -(-effective // CHARS_PER_PAGE) - FREE_PAGES)

print(f"text (excl. references): {body_chars:>7,} characters")
print(f"references (main.bbl):   {ref_chars:>7,} characters")
print(f"figures + tables:        {n_floats:>7} x {FLOAT_COST:,}")
print(f"effective total:         {int(effective):>7,} characters = {pages:.1f} pages")
print(f"estimated charge:        EUR {int(extra) * EUR_PER_PAGE} ({int(extra)} pages beyond {FREE_PAGES})")
if not bbl.exists():
    print("warning: main.bbl not found; run latexmk first", file=sys.stderr)

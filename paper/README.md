# Paper

Target: **Methods of Information in Medicine** (Thieme), Original Article, *Methods Print*
(subscription) track. Author instructions: `../../author_instructions_Methods.pdf`.

```bash
make              # build main.pdf
python budget.py  # estimated printed pages and page charge
make watch        # rebuild on save
make clean
```

## Length and cost

Methods Print is free for the first 5 printed pages: about 22,000 characters including
spaces, minus 1,500 per figure or table, references included. Each extra page costs
EUR 125; the first colour figure costs EUR 350. The agreed ceiling is 10 printed pages
(EUR 625), aiming for about 8, and all figures must be black and white. `budget.py`
applies this rule to `main.tex` and `main.bbl`.

## Format required at submission

- Microsoft Word (.docx), double-spaced, 12 pt, one column, line and page numbers.
  Convert with pandoc at the end.
- Structured abstract of at most 300 words: Background (optional), Objectives, Methods,
  Results, Conclusions; at most 5 keywords, MeSH preferred.
- Sections: Introduction, Objectives, Methods (ending with *Ethical considerations*),
  Results, Discussion (with a subsection on clinical or public health implications),
  Conclusions, Acknowledgments, Funding, Conflict of Interest, References.
- AMA references, numbered in order of citation, Index Medicus abbreviations.
- Figure captions after the references, tables after the captions; each figure as a
  separate TIFF/EPS file.
- ICMJE conflict-of-interest form for every author.
- A preprint deposited before submission is allowed; cite it and mention it in the
  cover letter. It also meets the ISCIII open-access requirement.

## Numbers

Every value in Results comes from the scripts and stored outputs under `eval/`. Do not
type a number that is not in `eval/results/`.

## History

The earlier draft for the Semantic Web Journal (22 July 2026) was replaced by this one;
a copy is in `../../workspace/swj-draft-2026-07-22.zip`. The empirical study over an
institutional REDCap instance (corpus B) is planned as a separate paper.

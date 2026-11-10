MAIN := main

.PHONY: all clean watch figures

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex refs.bib figures/fig1-architecture.pdf
	latexmk -pdf -interaction=nonstopmode -halt-on-error $(MAIN).tex

watch:
	latexmk -pdf -pvc -interaction=nonstopmode $(MAIN).tex

clean:
	latexmk -C
	rm -f $(MAIN).bbl

# Figure 1: PDF preview for the review copy; EPS and 1,200 dpi uncompressed TIFF to submit.
figures: figures/fig1-architecture.pdf
figures/fig1-architecture.pdf: figures/fig1-architecture.tex
	cd figures && pdflatex -interaction=nonstopmode -halt-on-error fig1-architecture.tex \
	  && pdftops -eps fig1-architecture.pdf fig1-architecture.eps \
	  && pdftoppm -r 1200 -mono -tiff -tiffcompression none -singlefile fig1-architecture.pdf fig1-architecture \
	  && rm -f fig1-architecture.aux fig1-architecture.log

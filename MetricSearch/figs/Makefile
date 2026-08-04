LX = pdflatex

all: query-radius.png query-knn.png pivots.png multiple-pivots.png compact-partitions.png probabilistic-spell.png lsh2.png quant.png graph1.png graph-construction.png graph-search.png graph-hierarchical.png graph-search-problems.png grafo-hsp-vs-otros.png

%.png: %.pdf
	pdftoppm -png -r 300 -singlefile $<  $(basename $< .pdf)

%.pdf: %.tex
	$(LX) $<

#query-radius.pdf: query-radius.tex
#	$(LX) query-radius.tex
#query-knn.pdf: query-knn.tex
#	$(LX) query-knn.tex
#
#pivots.pdf: pivots.tex
#	$(LX) pivots.tex
#
#multiple-pivots.pdf: multiple-pivots.tex
#	$(LX) multiple-pivots.tex
#
#compact-partitions.pdf: compact-partitions.tex
#	$(LX) compact-partitions.tex
#
#probabilistic-spell.pdf: probabilistic-spell.tex
#	$(LX) probabilistic-spell.tex
#
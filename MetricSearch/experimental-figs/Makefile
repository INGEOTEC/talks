all: fig-dist-Bit-distances.png fig-dist-lsqfit-cost-vs-n.png fig-dist-Point-cloud-distances.png \
	fig-dist-Population-distances.png fig-dist-Set-distances.png fig-dist-String-distances.png \
	fig-dist-Vector-distances.png \
	fig-performance-bench-abs+sota.png \
	fig-performance-lsqfit-recall-vs-cost.png \
	fig-performance-recall-vs-cost-per-quant-b=1.3.png \
	fig-performance-recall-vs-throughput-per-quant-b=1.3.png \
	fig-performance-laion-cost-vs-n.png

%.png: %.pdf
	pdftoppm -png -r 300 -singlefile $<  $(basename $< .pdf)


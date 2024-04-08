#!/bin/sh

for fname in MexLEF2023/*.qmd; 
    do quarto render /Users/mgraffg/software/talks/$fname; 
done

for fname in IberLEF2023/*.qmd; 
    do quarto render /Users/mgraffg/software/talks/$fname; 
done

quarto render .
quarto publish gh-pages . --no-browser
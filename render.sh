#!/bin/sh

for dirname in MexLEF2023 IberLEF2023 TextClassification;
do 
    for fname in $dirname/*.qmd; 
    do 
        quarto render $fname; 
    done
done

quarto render .
quarto publish gh-pages . --no-browser
# Paper dataset from ICML, NeurIPS and ICLR

The dataset contains all paper titles, authors and their affiliations from the
years

- ICML: 2017-2020
- NeurIPS: 2006-2020
- ICLR: 2018-2021

The earliest years are always the years in which the respective conference
introduced the web interface which this script is compatible with.

```csv
Conference,Year,Title,Author,Affiliation
NeurIPS,2006,Attentional Processing on a Spike-Based VLSI Neural Network,Yingxue Wang,"Swiss Federal Institute of Technology, Zurich"
NeurIPS,2006,Attentional Processing on a Spike-Based VLSI Neural Network,Rodney J Douglas,Institute of Neuroinformatics
NeurIPS,2006,Attentional Processing on a Spike-Based VLSI Neural Network,Shih-Chii Liu,"Institute for Neuroinformatics, University of Zurich and ETH Zurich"
NeurIPS,2006,Multi-Task Feature Learning,Andreas Argyriou,Ecole Centrale de Paris
# ...
```

## Update the Data

The first and definitely correct option is to just re-scrape the whole dataset as in the
following example.
```sh
python scrape.py 2006-2021
```

A faster alternative is just scraping the new data and appending it to the CSV file.
```sh
python scrape.py --output update.csv 2019-2021
cat update.csv >> papers.csv
```
The file is sorted by year, so appending at the end keeps the order in tact. However, you
need to take care that you do not end up with duplicate entries. Let's say that the
current file contains all papers until 2019 but when the file was created, only ICLR had
happened yet. If you then later scrape 2019 again to add the other conferences as above,
you would get the ICLR papers twice.

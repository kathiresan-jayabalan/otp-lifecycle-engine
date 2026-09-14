# Login Data Set for Risk-Based Authentication

`rba-sample.csv` in this directory is a hand-authored bootstrap sample that
follows the column layout of the public dataset (Wiefling, Jorgensen,
Thunem, Lo Iacono - Zenodo, 2022, doi:10.5281/zenodo.6782155). Values in it
are invented for wiring up the harness before the real dataset is fetched -
they are not drawn from the published data and should not be cited as such.

To pull the actual dataset for a real evaluation run:

```
npm run dataset:fetch
```

This calls the public Zenodo REST API for record 6782155, lists the files
attached to that record, and downloads the first CSV/zip entry to
`dataset/rba-full.csv` (gitignored - it's a multi-GB research dataset, not
something to commit). The dataset's own documentation restricts it to
research/testing use; do not point it at a production identity system.

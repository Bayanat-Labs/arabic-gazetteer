# arabic-gazetteer

**Build an Arabic place-names gazetteer for the 22 Arab League states from GeoNames and Wikidata. By Bayanat Labs.**

The builder downloads the GeoNames files for the 22 member states of the League of Arab States, joins them with the [Arab-World Wikidata Slice](https://huggingface.co/datasets/Bayanat-Labs/arab-world-wikidata), and writes four Parquet tables:

- `places`: one row per place with at least one Arabic name, with GeoNames and Wikidata IDs, the canonical Arabic name, coordinates, feature class, population, admin path and codes;
- `names`: one row per Arabic or Latin-script name, with source, language, GeoNames flags (preferred, short, colloquial, historic), validity dates and the spelling cluster it belongs to;
- `admin_units`: the countries and ADM1 to ADM4 units;
- `match_examples`: messy location strings mapped to a place, with same-name distractors and a fixed train/dev/test split, plus a baseline matcher.

The tables of release 0.1.0 are the Hugging Face dataset [Bayanat-Labs/arabic-gazetteer](https://huggingface.co/datasets/Bayanat-Labs/arabic-gazetteer): 246,637 places, 1,242,453 names, 8,282 admin units and 52,257 match examples, from the GeoNames files of 2026-10-30 and the Wikidata dump of 26 October 2026. The summary files of that release are in [`results/v0.1.0/`](results/v0.1.0/).

## Install

The PyPI package has not been released yet. Install from GitHub, pinned to the release tag:

```bash
pip install "git+https://github.com/Bayanat-Labs/arabic-gazetteer@v0.1.0"
```

Python 3.10 or later. Dependencies: requests, PyArrow, DuckDB and [arabic-normalize](https://github.com/Bayanat-Labs/arabic-normalize) (installed from GitHub at a fixed commit). The chart needs Matplotlib (`pip install matplotlib`).

## Build the gazetteer

```bash
# 1. GeoNames files for the 22 states (50 files, about 42 MB), one request at a time
arabic-gazetteer fetch-geonames geonames/

# 2. The Arab-World Wikidata Slice (Parquet, from Hugging Face), at the revision release 0.1.0 used
hf download Bayanat-Labs/arab-world-wikidata --repo-type dataset --revision 6e1295970ec41247d421e4843227f724ae8de32b --local-dir slice/

# 3. Tables, match examples, baseline, counts, chart and checks
arabic-gazetteer build --geonames geonames/ --wikidata slice/ --out release/ \
    --geonames-date 2026-10-30 --wikidata-date 2026-10-26 --wikidata-slice-revision 6e1295970ec41247d421e4843227f724ae8de32b
```

`build` checks the slice files it reads against the `SHA256SUMS` file shipped with the slice and stops if one differs. `meta/build.json` records the slice revision and the SHA-256 of the slice's `MANIFEST.json`, which is `afd93561c802ed4f8ecb6f3f4ea9e5a574b322ce10952b303f381c79fa601594` for this release.

`fetch-geonames` sends the User-Agent `BayanatLabs-OpenData/1.0 (+https://bayanatlabs.com/open; hello@bayanatlabs.com)`, waits at least 1.2 seconds between requests, records the Last-Modified date, size and SHA-256 of each file next to it, skips files already downloaded and stops on HTTP 403 or 429. GeoNames publishes new files every day, so a later download gives somewhat different tables; pass the date of your files to `--geonames-date`.

`build` holds the tables in memory (several GB for all 22 states) and takes a few minutes. It writes `data/<config>/*.parquet`, `meta/` (build information, counts, baseline, checks, per-state coverage) and `images/arabic_name_coverage.png`, and exits with status 1 if a check fails. `arabic-gazetteer stats release/` and `arabic-gazetteer validate release/` recompute the counts and the checks from the Parquet files.

The Wikidata class table `src/arabic_gazetteer/data/wikidata_class_families.csv` maps each P31 class used in the slice to a place family; `arabic-gazetteer class-map` rebuilds it from subclass-of (P279) rows of a Wikidata dump.

## Method

[docs/METHOD.md](docs/METHOD.md) gives the scope, the link rules, the canonical-name rule, the clusters, the admin paths and the match-example rules.

## Tests

```bash
pip install ".[test]"
python -m pytest -q
```

The tests run on small fixtures and need no network.

## Licence

- Code: Apache License 2.0 (`LICENSE`).
- Data files in `results/` and `src/arabic_gazetteer/data/`, and the documentation: CC BY 4.0 (`LICENSE-data`). Contains data from GeoNames (https://www.geonames.org), licensed under CC BY 4.0. Wikidata content is CC0 1.0.

Contact: hello@bayanatlabs.com

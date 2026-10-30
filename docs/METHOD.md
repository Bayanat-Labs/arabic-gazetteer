# Method

This page describes how `arabic-gazetteer build` makes the tables. The constants are in
`src/arabic_gazetteer/config.py`.

## Sources

- **GeoNames** (https://www.geonames.org, CC BY 4.0): the per-state files `<CC>.zip` (one row per
  feature) and `alternatenames/<CC>.zip` (one row per alternate name, with language code, the
  preferred, short, colloquial and historic flags and from/to dates), `admin1CodesASCII.txt`,
  `admin2Codes.txt`, `hierarchy.zip`, `countryInfo.txt` and `featureCodes_en.txt`, from
  https://download.geonames.org/export/dump/. All files are read as tab-separated UTF-8 text
  without quoting.
- **Wikidata** (CC0), through the Arab-World Wikidata Slice: the `entities` table (class group,
  P31 classes, labels, coordinates, states), `labels_long` (labels and aliases in `ar`, `arz`,
  `ary`, `en`, `fr`) and `triples` (truthy P17, P131, P1566, P1082, P1448, P1705 and P1813
  statements). Release 0.1.0 was built from Hugging Face revision `6e1295970ec41247d421e4843227f724ae8de32b` of the
  slice:

  ```bash
  hf download Bayanat-Labs/arab-world-wikidata --repo-type dataset --revision 6e1295970ec41247d421e4843227f724ae8de32b --local-dir slice/
  ```

  `build` checks the files it reads against the `SHA256SUMS` file shipped with the slice and
  stops if one differs. It records the revision given with `--wikidata-slice-revision` and the
  SHA-256 of the slice's `MANIFEST.json` in `meta/build.json`.

## Scope

The 22 GeoNames country codes DZ BH KM DJ EG IQ JO KW LB LY MR MA OM PS QA SA SO SD SY TN AE YE.
Feature classes A, P, H, T, L, V and U, and from class S the codes AIRP, AIRF, PRT, UNIV, HSP,
CSTL, FT, ANS, RUIN, MUS and RSTN.

## Names

- Arabic names: GeoNames alternate names with an Arabic language code (`ar`, `arb`, `arz`, `ary`,
  `arq`, `afb`, `apc`, `ajp`, `acm`, `aeb`, `ars` and other Arabic varieties) and Wikidata
  labels, aliases and name statements in `ar`, `arz` and `ary`. A name counts as Arabic when at
  least 90% of its letters are Arabic-script letters.
- Latin-script names: the GeoNames main name and ASCII name, GeoNames alternate names in `en`,
  `fr` or without a language code, and Wikidata labels, aliases and name statements in `en` and
  `fr`.
- GeoNames pseudo-language codes are not names: `iata`, `icao`, `faac`, `unlc`, `post` and `abbr`
  go to `codes`, `link` to `wikipedia_links`, and `wkdt` is used for the Wikidata link.
- GeoNames alternate names in other languages are not part of the tables.
- A name whose script does not match its language tag is kept with `name_issue`
  (`not_arabic_script`, `arabic_script_in_latin_slot`, `not_latin_script`); Arabic names with
  the letters پ چ ژ گ ڤ ڨ ک ی and similar carry `extended_letters`.
- Invisible format controls (U+200B to U+200F, U+202A to U+202E, U+2066 to U+2069, U+061C and
  U+FEFF) are removed before the script test, the keys and the choice of canonical names. The
  `name` column of the `names` table keeps the source string (NFC, spaces collapsed); a name that
  contains format controls carries `format_control` in `name_issue`. A name with a script issue
  as well lists both, separated by a comma. `name_ar`, `name_en`, `names_ar`, `names_latin`, the
  admin-path names and the match examples use names without format controls.

## Keys and clusters

- Arabic cluster key (`name_norm`): arabic-normalize with the `bayanat-norm-v1` policy, then
  whitespace collapsed.
- Latin cluster key: compatibility decomposition, combining marks removed, case folded, ʿ ʾ and
  apostrophes removed, other punctuation and hyphens read as spaces.
- A cluster is the set of names of one record with the same script and cluster key. Clusters
  never contain names of two records.
- Matching key (`match_key`): for Arabic, the cluster key with ة→ه, ؤ→و, ئ→ي, ء removed, Persian
  letter forms mapped to Arabic ones, punctuation removed and ال removed at the start of each
  word of four or more letters; for Latin, the cluster key with articles (al, el, ash ...)
  removed before another word, doubled letters collapsed, final -ah/-eh read as -a, ou→u, ee→i,
  oo→u.
- `name_family_id` is a hash of the matching key; different places with the same name share it.

## Records

1. Each GeoNames feature in scope gets its names. Its Wikidata link candidates are the items whose
   P1566 is the feature's ID and the item named by the feature's `wkdt` alternate name.
2. A candidate is accepted when the item is in the slice and the coordinates are within 10 km
   (P and S features; 30 km for P features with a population of 100,000 or more) or 50 km
   (other classes). Accepted links are ordered: stated on both sides, more sitelinks, shorter
   distance. The first is the record's `wikidata_qid`; its names are added to the record.
3. The feature is a record when it then has at least one Arabic name.
4. A Wikidata item is a Wikidata-only record when it is in the place class group of the slice,
   has a P17 statement for one of the 22 states, coordinates and an Arabic label, has no accepted
   link to a GeoNames feature in scope, and its P31 classes put it in a kept family. The family of
   a class is the family of the root it reaches in the fewest P279 steps (ties: P, A, S, H, T, V,
   L, then X): P human settlement or neighbourhood; A administrative territorial entity; S
   airport, port, university, hospital, castle, fortification, archaeological site, ruins, museum
   or railway station; H body of water, watercourse, spring, well or wadi; T landform, mountain
   or island; V forest; L geographic region or protected area; X (not kept) architectural
   structure, building, place of worship, road, infrastructure, facility, business, organisation
   or educational institution.

## Canonical names

`name_ar`: a GeoNames Arabic name marked preferred and neither historic nor colloquial (lowest
alternate-name ID first); else the Wikidata label in `ar`, `arz`, then `ary`; else the
non-historic GeoNames Arabic name whose cluster key is most frequent (lowest ID first); else
another Arabic name from Wikidata. Names with a script issue other than `extended_letters` are
not used, and `extended_letters` names only when nothing else is left. Format controls do not
count as an issue here; they are removed from the chosen name.

`name_en`: a GeoNames English name marked preferred; else the Wikidata English label; else
another GeoNames English name; else the GeoNames main name; else the Wikidata French label,
without format controls.

## Admin paths

Level 0 is the country. Levels 1 and 2 come from the admin1 and admin2 codes files, levels 3 and
4 from ADM3 and ADM4 features with the same codes. Each record lists levels 1 to the deepest
level that GeoNames uses in its state (for an admin unit, the levels above it; for a country,
none). A level whose code is empty, `00` or unknown is `unresolved` with empty IDs and names.
Wikidata-only records take the path of the first GeoNames record reached by walking P131 upward
(up to 12 steps, same state).

`parent_place_ids`: populated places that the GeoNames hierarchy file gives as parents (for
example a district of a city).

`hierarchy_check`: for records with a Wikidata item, P131 is walked upward to the first items
linked to GeoNames records. `agree` when one of them is in the record's GeoNames path or parents,
or its own path matches the record's path at each level where both are resolved; `disagree` when
none does and at least one could be compared; `not_compared` otherwise.

## Possible duplicates

GeoNames records with the same state, feature code, Arabic matching key and coordinates rounded to
three decimals point to the one with the lowest ID. A Wikidata-only record points to the nearest
GeoNames record within 2 km that has the same Arabic matching key.

## Match examples

- Targets: P and A records that are not possible duplicates. Per state, up to 1,500 targets: 90%
  from names shared by at least two other records, 10% from names no other record shares, in a
  fixed hash order.
- Up to three strings per target: (1) an Arabic string: another Arabic name of the record, a
  one-rule spelling change of the canonical name (ة→ه, hamza on alef removed or added, ى↔ي,
  article removed or added, hamza seats folded, compound joined), or one letter dropped or two
  letters swapped; (2) a Latin-script name of the record, as given or in capitals or lower case
  without diacritics or hyphens; (3) the name followed by its parent place or an admin unit
  (Arabic or Latin), with a comma, an Arabic comma or a dash; districts get the word حي or "Dist.".
- `distractor_ids`: up to ten other records in the same name family (and, for Latin strings, the
  same Latin name family), same state first.
- `jurisdiction_hint`: the target's state for half of the targets, by hash.
- `split`: a hash of the admin1 code (or the state when admin1 is unresolved) puts 70% of the
  units in train, 10% in dev and 20% in test.

## Baseline

Every name is indexed as written (without format controls), by matching key and by matching key
without a leading generic word. An input is split at commas, Arabic commas, semicolons and " - "; the first part is looked
up in the three indexes in turn; the other parts must match a name of one of the candidate's admin
units or parent places. Ties go to the larger population, then capitals and admin seats, then more
resolved admin levels, then the lowest `record_id`. The exact-string baseline looks up the whole
input as written.

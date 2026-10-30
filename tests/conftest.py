"""Small GeoNames and Wikidata fixtures written to a temporary folder."""
from __future__ import annotations

import os
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

T = "\t"


def geoname(gid, name, ascii_, lat, lon, fclass, fcode, cc="SA", a1="", a2="", pop=0):
    return T.join([str(gid), name, ascii_, "", str(lat), str(lon), fclass, fcode, cc, "", a1, a2, "", "",
                   str(pop), "", "0", "Asia/Riyadh", "2025-01-01"])


def alt(aid, gid, lang, name, pref="", short="", colloq="", hist="", frm="", to=""):
    return T.join([str(aid), str(gid), lang, name, pref, short, colloq, hist, frm, to])


GEONAMES_SA = [
    geoname(102358, "Saudi Arabia", "Saudi Arabia", 25.0, 45.0, "A", "PCLI", a1="00", pop=30000000),
    geoname(104514, "Makkah Region", "Makkah Region", 21.5, 41.0, "A", "ADM1", a1="14"),
    geoname(108411, "Riyadh Region", "Riyadh Region", 24.5, 45.5, "A", "ADM1", a1="10"),
    geoname(900001, "Jeddah Governorate", "Jeddah Governorate", 21.6, 39.2, "A", "ADM2", a1="14", a2="900001"),
    geoname(105343, "Jeddah", "Jeddah", 21.49012, 39.18624, "P", "PPL", a1="14", pop=4697000),
    geoname(900010, "Al Nuzhah", "Al Nuzhah", 21.55, 39.20, "P", "PPLX", a1="14", a2="900001"),
    geoname(900011, "An Nuzhah", "An Nuzhah", 24.70, 46.70, "P", "PPLX", a1="10"),
    geoname(900012, "Al Nuzhah", "Al Nuzhah", 26.40, 50.10, "P", "PPL", a1="06"),
    geoname(900020, "Wadi Example", "Wadi Example", 22.0, 40.0, "H", "WAD", a1="14"),
    geoname(900030, "Example School", "Example School", 21.5, 39.2, "S", "SCH", a1="14"),
    geoname(900040, "Qaryat Wikidata", "Qaryat Wikidata", 23.0, 41.0, "P", "PPL", a1="14"),
    geoname(900050, "No Arabic", "No Arabic", 23.5, 41.5, "P", "PPL", a1="14"),
]
ALT_SA = [
    alt(1, 102358, "ar", "السعودية", pref="1", short="1"),
    alt(2, 104514, "ar", "منطقة مكة المكرمة"),
    alt(3, 108411, "ar", "منطقة الرياض"),
    alt(4, 900001, "ar", "محافظة جدة"),
    alt(10, 105343, "ar", "جدة"),
    alt(11, 105343, "ar", "جدّة"),
    alt(12, 105343, "arz", "جده"),
    alt(13, 105343, "", "Jiddah"),
    alt(14, 105343, "", "Jidda"),
    alt(15, 105343, "en", "Jeddah"),
    alt(16, 105343, "fr", "Djeddah"),
    alt(17, 105343, "iata", "JED"),
    alt(18, 105343, "link", "https://en.wikipedia.org/wiki/Jeddah"),
    alt(19, 105343, "wkdt", "Q374365"),
    alt(20, 105343, "ar", "Jiddah"),          # Latin text tagged as Arabic
    alt(21, 105343, "ar", "جدة القديمة", hist="1", frm="1900", to="1950"),
    alt(30, 900010, "ar", "حي النزهة", pref="1"),
    alt(31, 900011, "ar", "النزهة"),
    alt(32, 900012, "ar", "النزهة"),
    # invisible format controls: the record keeps them out of name_ar, name_en and the name lists,
    # the name rows keep the source strings and carry name_issue format_control
    alt(40, 900020, "ar", "\u202bوادي المثال\u202c"),
    alt(41, 900020, "en", "Wadi Ex\u200bample"),
    alt(42, 900020, "ar", "گرمسير\u200e"),
    alt(33, 900011, "ar", "النزهة\u200f"),
    alt(50, 900030, "ar", "مدرسة المثال"),
    alt(60, 900040, "wkdt", "Q900040"),
]
HIERARCHY = ["105343\t900010\t", "102358\t104514\tADM"]
ADMIN1 = ["SA.14\tMakkah Region\tMakkah Region\t104514", "SA.10\tRiyadh Region\tRiyadh Region\t108411"]
ADMIN2 = ["SA.14.900001\tJeddah Governorate\tJeddah Governorate\t900001"]
COUNTRY = ["#ISO\tISO3\tISO-Numeric\tfips\tCountry", "\t".join(
    ["SA", "SAU", "682", "SA", "Saudi Arabia", "Riyadh", "1960582", "34268528", "AS", ".sa", "SAR", "Rial",
     "966", "#####", "^(\\d{5})$", "ar-SA", "102358", "QA,OM,IQ,YE,JO,AE,KW", ""])]
FEATURE_CODES = ["P.PPL\tpopulated place\ta city, town, village", "P.PPLX\tsection of populated place\t"]


def _zip(path, member, lines):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, "\n".join(lines) + "\n")


@pytest.fixture(scope="session")
def geonames_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("geonames")
    os.makedirs(d / "alternatenames")
    _zip(d / "SA.zip", "SA.txt", GEONAMES_SA)
    _zip(d / "alternatenames" / "SA.zip", "SA.txt", ALT_SA)
    _zip(d / "hierarchy.zip", "hierarchy.txt", HIERARCHY)
    (d / "admin1CodesASCII.txt").write_text("\n".join(ADMIN1) + "\n", encoding="utf-8")
    (d / "admin2Codes.txt").write_text("\n".join(ADMIN2) + "\n", encoding="utf-8")
    (d / "countryInfo.txt").write_text("\n".join(COUNTRY) + "\n", encoding="utf-8")
    (d / "featureCodes_en.txt").write_text("\n".join(FEATURE_CODES) + "\n", encoding="utf-8")
    (d / "readme.txt").write_text("fixture\n", encoding="utf-8")
    return str(d)


ENTITIES = [
    # qid, class_group, p31, label_ar, label_en, lat, lon, countries, n_sitelinks
    ("Q851", "place", ["Q6256"], "السعودية", "Saudi Arabia", 24.0, 45.0, ["SA"], 300),
    ("Q374365", "place", ["Q486972"], "جدة", "Jeddah", 21.5433, 39.1728, ["SA"], 150),
    ("Q900040", "place", ["Q532"], "قرية ويكي", "Wikidata Village", 23.001, 41.001, ["SA"], 3),
    ("Q900060", "place", ["Q532"], "قرية جديدة", "New Village", 22.5, 40.5, ["SA"], 1),
    ("Q900070", "place", ["Q32815"], "مسجد المثال", "Example Mosque", 21.5, 39.2, ["SA"], 1),
    ("Q900080", "place", ["Q532"], None, "No Arabic Label", 22.6, 40.6, ["SA"], 1),
    ("Q900090", "place", ["Q532"], "النزهة", "An Nuzhah", 26.401, 50.101, ["SA"], 1),
    ("Q900001", "place", ["Q15"], "محافظة جدة", "Jeddah Governorate", 21.6, 39.2, ["SA"], 5),
]
TRIPLES = [
    ("Q374365", "P1566", None, "105343"), ("Q374365", "P17", "Q851", None), ("Q374365", "P131", "Q900001", None),
    ("Q900001", "P1566", None, "900001"), ("Q900001", "P17", "Q851", None),
    ("Q900060", "P17", "Q851", None), ("Q900060", "P131", "Q900001", None),
    ("Q900070", "P17", "Q851", None), ("Q900080", "P17", "Q851", None), ("Q900090", "P17", "Q851", None),
    ("Q900040", "P17", "Q851", None), ("Q851", "P1566", None, "102358"),
    ("Q374365", "P1448", None, "جدة"),
]
CLASSES = [  # class, family, steps, root
    ("Q6256", "A", 2, "Q56061"), ("Q486972", "P", 0, "Q486972"), ("Q532", "P", 2, "Q486972"),
    ("Q32815", "X", 1, "Q1370598"), ("Q15", "A", 1, "Q56061"),
]


@pytest.fixture(scope="session")
def wikidata_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("slice")
    ent = {
        "qid": [], "class_group": [], "p31": [], "label_ar": [], "label_en": [], "lat": [], "lon": [],
        "countries_iso2": [], "lastrevid": [], "n_sitelinks": [],
    }
    labels = {"qid": [], "lang": [], "kind": [], "value": []}
    for qid, g, p31, ar, en, lat, lon, cc, nsl in ENTITIES:
        for k, v in zip(ent, (qid, g, p31, ar, en, lat, lon, cc, 1, nsl)):
            ent[k].append(v)
        for lang, v in (("ar", ar), ("en", en)):
            if v:
                labels["qid"].append(qid)
                labels["lang"].append(lang)
                labels["kind"].append("label")
                labels["value"].append(v)
    labels["qid"].append("Q374365")
    labels["lang"].append("en")
    labels["kind"].append("alias")
    labels["value"].append("Jidda")
    tri = {"qid": [], "pid": [], "rank": [], "truthy": [], "value_qid": [], "value_string": [], "value_lang": [],
           "value_amount": [], "value_time": []}
    for qid, pid, vq, vs in TRIPLES:
        for k, v in zip(tri, (qid, pid, "normal", True, vq, vs, "ar" if pid == "P1448" else None, None, None)):
            tri[k].append(v)
    for cfg, cols in (("entities", ent), ("labels_long", labels), ("triples", tri)):
        os.makedirs(d / "data" / cfg)
        pq.write_table(pa.table(cols), d / "data" / cfg / "train-00000-of-00001.parquet")
    return str(d)


@pytest.fixture(scope="session")
def class_map_csv(tmp_path_factory):
    p = tmp_path_factory.mktemp("cm") / "classes.csv"
    lines = ["class_qid,family,steps,root_qid"] + [f"{c},{f},{s},{r}" for c, f, s, r in CLASSES]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


@pytest.fixture(scope="session")
def built(geonames_dir, wikidata_dir, class_map_csv):
    from arabic_gazetteer import build, geonames, wikidata
    from arabic_gazetteer.config import QID_TO_STATE

    gn = geonames.read(geonames_dir, ["SA"])
    items = wikidata.read(wikidata_dir, QID_TO_STATE)
    cmap = wikidata.read_class_map(class_map_csv)
    return build.build(gn, items, cmap, "2026-10-30", "2026-10-26")


@pytest.fixture(scope="session")
def release(tmp_path_factory, geonames_dir, wikidata_dir, class_map_csv):
    """A release folder written by the CLI from the fixtures."""
    from arabic_gazetteer.cli import main

    out = tmp_path_factory.mktemp("release")
    rc = main(["build", "--geonames", geonames_dir, "--wikidata", wikidata_dir, "--out", str(out),
               "--geonames-date", "2026-10-30", "--wikidata-date", "2026-10-26", "--class-map", class_map_csv,
               "--states", "SA", "--min-examples", "1", "--min-distractor-share", "0"])
    assert rc == 0
    return str(out)

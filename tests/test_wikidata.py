from arabic_gazetteer import wikidata
from arabic_gazetteer.config import QID_TO_STATE


def test_read_slice(wikidata_dir):
    items = wikidata.read(wikidata_dir, QID_TO_STATE)
    it = items["Q374365"]
    assert it.labels["ar"] == "جدة" and it.aliases["en"] == ["Jidda"]
    assert it.p1566 == [105343] and it.p17_states == ["SA"] and it.p131 == ["Q900001"]
    assert it.names == [("P1448", "ar", "جدة")]
    assert it.n_sitelinks == 150


def test_class_families():
    parents = {
        "Q32815": ["Q1370598"], "Q1370598": ["Q41176"], "Q41176": ["Q811979"],
        "Q532": ["Q486972"], "Q486972": ["Q2221906"],
        "Q15": ["Q56061"], "Q839954": ["Q2221906"],
        "Q100": ["Q41176", "Q486972"],   # tie at one step: the family listed first wins (P before X)
    }
    fam = wikidata.class_families(parents, ["Q32815", "Q532", "Q15", "Q839954", "Q100", "Q999"])
    assert fam["Q32815"][0] == "X"
    assert fam["Q532"] == ("P", 1, "Q486972")
    assert fam["Q15"][0] == "A"
    assert fam["Q839954"] == ("S", 0, "Q839954")
    assert fam["Q100"][0] == "P"
    assert fam["Q999"][0] == "-"


def test_class_map_roundtrip(tmp_path):
    p = tmp_path / "m.csv"
    wikidata.write_class_map(str(p), {"Q532": ("P", 1, "Q486972"), "Q9": ("-", None, None)})
    m = wikidata.read_class_map(str(p))
    assert m == {"Q532": ("P", 1, "Q486972"), "Q9": ("-", None, None)}


def test_shipped_class_map_reads():
    from arabic_gazetteer.cli import _class_map_path

    m = wikidata.read_class_map(_class_map_path())
    assert m["Q32815"][0] == "X" and m["Q532"][0] == "P"


def test_verify_slice(wikidata_dir, tmp_path):
    import hashlib
    import shutil

    import pytest

    # a folder without SHA256SUMS is read as it is
    assert wikidata.verify_slice(wikidata_dir)["sha256sums_checked"] is False
    d = tmp_path / "slice"
    shutil.copytree(wikidata_dir, d)
    lines = []
    for cfg in wikidata.READ_CONFIGS:
        rel = f"data/{cfg}/train-00000-of-00001.parquet"
        lines.append(f"{hashlib.sha256((d / rel).read_bytes()).hexdigest()}  {rel}")
    (d / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (d / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
    res = wikidata.verify_slice(str(d))
    assert res["files_checked"] == 3
    assert res["manifest_sha256"] == hashlib.sha256(b"{}\n").hexdigest()
    with open(d / "data" / "triples" / "train-00000-of-00001.parquet", "ab") as fh:
        fh.write(b"x")
    with pytest.raises(ValueError):
        wikidata.verify_slice(str(d))

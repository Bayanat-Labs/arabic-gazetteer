import json
import os

import pyarrow.parquet as pq

from arabic_gazetteer import package, stats, validate


def test_release_files(release):
    for cfg in ("places", "names", "admin_units"):
        files = os.listdir(os.path.join(release, "data", cfg))
        assert files and all(f.endswith(".parquet") for f in files)
    for split in ("train", "dev", "test"):
        assert os.path.exists(os.path.join(release, "data", "match_examples", f"{split}.parquet"))
    t = pq.read_table(os.path.join(release, "data", "places", "train-00000-of-00001.parquet"))
    assert t.schema.equals(package.PLACES, check_metadata=False)
    for f in ("state_coverage.csv", "baseline.json", "build.json", "stats.json", "validation.json"):
        assert os.path.exists(os.path.join(release, "meta", f))
    assert os.path.exists(os.path.join(release, "images", "arabic_name_coverage.png"))


def test_validation_passes(release):
    res = validate.run(release, min_examples=1, min_distractor_share=0)
    assert all(ok for _, ok, _ in res), [n for n, ok, _ in res if not ok]


def test_stats_from_release(release):
    st = stats.compute(release)
    assert st["places"] == len(pq.read_table(os.path.join(release, "data", "places")).to_pylist())
    sa = [r for r in st["per_state"] if r["country_code"] == "SA"][0]
    assert sa["places"] == st["places"]
    assert 0 < sa["arabic_name_coverage"] <= 1


def test_build_info(release):
    with open(os.path.join(release, "meta", "build.json"), encoding="utf-8") as fh:
        info = json.load(fh)
    assert info["normalisation"]["policy"] == "bayanat-norm-v1"
    assert info["normalisation"]["policy_sha256"].startswith("ebdb8200")
    assert info["geonames"]["date"] == "2026-10-30"
    assert set(info["wikidata"]) >= {"slice_revision", "slice_manifest_sha256",
                                     "slice_files_checked_against_sha256sums"}


def test_validation_catches_format_controls(release, tmp_path):
    import shutil

    import pyarrow as pa

    bad = tmp_path / "bad"
    shutil.copytree(release, bad)
    f = bad / "data" / "places" / "train-00000-of-00001.parquet"
    t = pq.read_table(f)
    names = t.column("name_ar").to_pylist()
    names[0] = names[0] + "\u200e"
    pq.write_table(t.set_column(t.schema.get_field_index("name_ar"), "name_ar",
                                pa.array(names, pa.string())), f)
    fn = bad / "data" / "names" / "train-00000-of-00001.parquet"
    t = pq.read_table(fn)
    issues = [None] * t.num_rows
    pq.write_table(t.set_column(t.schema.get_field_index("name_issue"), "name_issue",
                                pa.array(issues, pa.string())), fn)
    res = {n: ok for n, ok, _ in validate.run(str(bad), min_examples=1, min_distractor_share=0)}
    assert not res["no canonical, listed or admin-unit name contains an invisible format control"]
    assert not res["name rows with invisible format controls, and only those, carry name_issue format_control"]
    assert res["record_id unique"]


def test_stats_count_format_controls(release):
    st = stats.compute(release)
    assert st["name_issues"]["format_control"] == 4
    assert st["name_issues"]["extended_letters"] >= 1
    assert st["name_rows_with_two_issues"] == 1

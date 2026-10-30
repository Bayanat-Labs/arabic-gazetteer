"""Command line: arabic-gazetteer fetch-geonames | class-map | build | stats | validate."""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import sys
from importlib import resources

from . import __version__

CLASS_MAP = "wikidata_class_families.csv"


def _class_map_path() -> str:
    return str(resources.files("arabic_gazetteer").joinpath("data", CLASS_MAP))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_fetch(a) -> int:
    from . import geonames

    geonames.fetch(a.out, a.states.split(",") if a.states else None)
    return 0


def cmd_class_map(a) -> int:
    import duckdb

    from . import wikidata

    ent = sorted(glob.glob(os.path.join(a.slice, "data", "entities", "*.parquet")))
    classes = [r[0] for r in duckdb.connect().execute(
        "select distinct unnest(p31) from read_parquet(?) where class_group <> 'human'", [ent]).fetchall()]
    parents = wikidata.load_p279(a.p279)
    fams = wikidata.class_families(parents, classes)
    wikidata.write_class_map(a.out, fams)
    print(f"{len(fams)} classes -> {a.out}")
    return 0


def cmd_build(a) -> int:
    from arabic_normalize import normalize_detailed

    from . import build, geonames, match, package, stats, validate, wikidata
    from .config import QID_TO_STATE, STATES

    gn = geonames.read(a.geonames, a.states.split(",") if a.states else None)
    print(f"GeoNames: {len(gn.features)} features read")
    slice_check = wikidata.verify_slice(a.wikidata)
    if slice_check["sha256sums_checked"]:
        print(f"Wikidata slice: {slice_check['files_checked']} files match the slice's SHA256SUMS")
    items = wikidata.read(a.wikidata, QID_TO_STATE)
    print(f"Wikidata slice: {len(items)} items read")
    cmap = wikidata.read_class_map(a.class_map or _class_map_path())
    res = build.build(gn, items, cmap, a.geonames_date, a.wikidata_date)
    places, names = res["places"], res["names"]
    package.name_ids(names)
    print(f"{len(places)} places, {len(names)} names, {len(res['admin_units'])} admin units")
    out = a.out
    for cfg in ("places", "names", "admin_units"):
        for old in glob.glob(os.path.join(out, "data", cfg, "*.parquet")):
            os.remove(old)
    package.write_config(places, "places", out)
    package.write_config(names, "names", out)
    package.write_config(res["admin_units"], "admin_units", out)
    ex = match.generate(places, names)
    package.write_match_examples(ex, out)
    print(f"{len(ex)} match examples")
    os.makedirs(os.path.join(out, "meta"), exist_ok=True)
    with open(os.path.join(out, "meta", "state_coverage.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res["coverage"][0]))
        w.writeheader()
        w.writerows(res["coverage"])
    base = match.evaluate(ex, places, names)
    with open(os.path.join(out, "meta", "baseline.json"), "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False, indent=1)
    files = []
    for meta in sorted(glob.glob(os.path.join(a.geonames, "**", "*.meta.json"), recursive=True)):
        with open(meta, encoding="utf-8") as fh:
            m = json.load(fh)
        files.append({k: m.get(k) for k in ("source_url", "last_modified", "bytes", "sha256", "retrieved_at")})
    wd_meta = wikidata.read_slice_meta(a.wikidata)
    r = normalize_detailed("جدة")
    import arabic_normalize
    info = {
        "release": __version__,
        "geonames": {"date": a.geonames_date, "files": files},
        "wikidata": {"slice": wikidata.SLICE_REPO, "slice_version": a.wikidata_slice_version,
                     "slice_revision": a.wikidata_slice_revision,
                     "slice_manifest_sha256": slice_check["manifest_sha256"],
                     "slice_files_checked_against_sha256sums": slice_check["files_checked"],
                     "dump_file": wd_meta.get("file"), "dump_date": a.wikidata_date,
                     "dump_sha256": (wd_meta.get("computed_checksums") or {}).get("sha256")},
        "normalisation": {"package": "arabic-normalize", "package_version": arabic_normalize.__version__,
                          "policy": "bayanat-norm-v1", "policy_sha256": r.policy_hash},
        "build_counts": res["stats"],
        "class_map_sha256": _sha256(a.class_map or _class_map_path()),
        "states": list(STATES),
    }
    with open(os.path.join(out, "meta", "build.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    stats.write(out)
    res_v = validate.write(out, min_examples=a.min_examples, min_distractor_share=a.min_distractor_share)
    failed = [n for n, ok, _ in res_v if not ok]
    print(f"checks: {len(res_v) - len(failed)} of {len(res_v)} pass")
    for n in failed:
        print("FAIL", n)
    return 1 if failed else 0


def cmd_stats(a) -> int:
    from . import stats

    st = stats.write(a.release)
    print(json.dumps({k: v for k, v in st.items() if k != "per_state"}, ensure_ascii=False, indent=1))
    return 0


def cmd_validate(a) -> int:
    from . import validate

    res = validate.write(a.release, min_examples=a.min_examples, min_distractor_share=a.min_distractor_share)
    for n, ok, d in res:
        print("PASS" if ok else "FAIL", n, d)
    return 0 if all(ok for _, ok, _ in res) else 1


def _limits(s) -> None:
    s.add_argument("--min-examples", type=int, default=5000, help="smallest number of match examples")
    s.add_argument("--min-distractor-share", type=float, default=0.8,
                   help="smallest share of match examples with two or more distractors")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="arabic-gazetteer", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fetch-geonames", help="download the GeoNames files for the 22 states")
    s.add_argument("out")
    s.add_argument("--states", help="comma-separated GeoNames country codes (default: all 22)")
    s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("class-map", help="rebuild the Wikidata class -> family table")
    s.add_argument("--p279", required=True, help="folder of classes_*.jsonl.zst rows {id, p279}")
    s.add_argument("--slice", required=True, help="local copy of the Arab-World Wikidata Slice")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_class_map)
    s = sub.add_parser("build", help="build the release tables")
    s.add_argument("--geonames", required=True, help="folder written by fetch-geonames")
    s.add_argument("--wikidata", required=True, help="local copy of the Arab-World Wikidata Slice")
    s.add_argument("--out", required=True)
    s.add_argument("--geonames-date", required=True, help="date of the GeoNames files, YYYY-MM-DD")
    s.add_argument("--wikidata-date", required=True, help="date of the Wikidata dump, YYYY-MM-DD")
    s.add_argument("--wikidata-slice-version", default="0.1.0")
    s.add_argument("--wikidata-slice-revision",
                   help="Hugging Face commit of the slice that was downloaded (recorded in meta/build.json)")
    s.add_argument("--class-map", help="class map CSV (default: the one shipped with the package)")
    s.add_argument("--states", help="comma-separated GeoNames country codes to read (default: all 22)")
    _limits(s)
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("stats", help="recompute meta/stats.json and the chart from a release folder")
    s.add_argument("release")
    s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("validate", help="run the checks on a release folder")
    s.add_argument("release")
    _limits(s)
    s.set_defaults(fn=cmd_validate)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

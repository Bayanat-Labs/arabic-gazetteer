"""Checks on the released files. Each check returns (name, passed, detail)."""
from __future__ import annotations

import glob
import json
import os
from collections import Counter

from .config import STATES
from .textnorm import FORMAT_CONTROL_ISSUE, has_format_controls, name_issues, script_of, visible


def _read(release, config, columns=None):
    import pyarrow.parquet as pq

    rows = []
    for f in sorted(glob.glob(os.path.join(release, "data", config, "*.parquet"))):
        rows += pq.read_table(f, columns=columns).to_pylist()
    return rows


def run(release: str, min_examples: int = 5000, min_distractor_share: float = 0.8) -> list[tuple[str, bool, str]]:
    places = _read(release, "places")
    names = _read(release, "names", ["name_id", "record_id", "name", "is_arabic", "is_canonical_ar",
                                     "source_license", "cluster_id", "script", "name_issue"])
    units = _read(release, "admin_units", ["geoname_id", "parent_geoname_id", "level", "country_code",
                                           "name_ar", "name_en"])
    ex = _read(release, "match_examples")
    out = []

    def check(name, ok, detail=""):
        out.append((name, bool(ok), detail))

    ids = [p["record_id"] for p in places]
    check("record_id unique", len(ids) == len(set(ids)), f"{len(ids)} records")
    pid = set(ids)
    gids = [p["geoname_id"] for p in places if p["geoname_id"] is not None]
    check("one record per GeoNames feature", len(gids) == len(set(gids)))
    wd_only = {p["wikidata_qid"] for p in places if p["source"] == "wikidata"}
    linked = {p["wikidata_qid"] for p in places if p["source"] == "geonames+wikidata"}
    check("Wikidata-only items are not linked to a GeoNames record", not (wd_only & linked))
    bad = [p["record_id"] for p in places if p["latitude"] is None or p["longitude"] is None
           or not (-90 <= p["latitude"] <= 90 and -180 <= p["longitude"] <= 180)]
    check("every record has coordinates", not bad, f"{len(bad)} without")
    bad = [p["record_id"] for p in places if p["country_code"] not in STATES]
    check("every record has one of the 22 country codes", not bad, f"{len(bad)} without")
    bad = [p["record_id"] for p in places if not p["name_ar"] or script_of(p["name_ar"]) != "Arab"]
    check("canonical Arabic name is in Arabic script", not bad, f"{len(bad)} failing")
    bad = [p["record_id"] for p in places
           if any(has_format_controls(x) for x in [p["name_ar"], p["name_en"]] + list(p["names_ar"])
                  + list(p["names_latin"]) + [n[k] for n in p["admin_path"] for k in ("name_ar", "name_en")])]
    bad += [u["geoname_id"] for u in units if has_format_controls(u["name_ar"]) or has_format_controls(u["name_en"])]
    check("no canonical, listed or admin-unit name contains an invisible format control", not bad,
          f"{len(bad)} failing")
    bad = [p["record_id"] for p in places if p["license_partition"] != "cc-by-4.0" or not p["source_refs"]]
    check("licence partition and source references on every record", not bad, f"{len(bad)} failing")
    bad = [p["record_id"] for p in places if p["hierarchy_conflict"] != (p["hierarchy_check"] == "disagree")]
    check("hierarchy_conflict matches hierarchy_check", not bad)

    bad = 0
    for p in places:
        path = p["admin_path"]
        if not path or path[0]["level"] != 0 or path[0]["code"] != p["country_code"]:
            bad += 1
            continue
        if [n["level"] for n in path] != list(range(len(path))):
            bad += 1
            continue
        for n in path[1:]:
            if n["status"] == "unresolved" and (n["geoname_id"] is not None or n["name_ar"] is not None):
                bad += 1
            if n["status"] == "resolved" and n["geoname_id"] is None:
                bad += 1
        if p["admin_levels"] != len(path) - 1:
            bad += 1
    check("admin paths start at the country, list every level, and keep unresolved levels empty", bad == 0,
          f"{bad} failing")

    nid = [n["name_id"] for n in names]
    check("name_id unique", len(nid) == len(set(nid)), f"{len(nid)} names")
    orphan = sum(1 for n in names if n["record_id"] not in pid)
    check("every name belongs to a record", orphan == 0, f"{orphan} orphan names")
    canon = Counter(n["record_id"] for n in names if n["is_canonical_ar"])
    check("exactly one canonical Arabic name per record", len(canon) == len(pid) and set(canon.values()) == {1})
    name_of = {p["record_id"]: p["name_ar"] for p in places}
    bad = sum(1 for n in names if n["is_canonical_ar"] and visible(n["name"]) != name_of.get(n["record_id"]))
    check("canonical name row (without format controls) equals the record's name_ar", bad == 0, f"{bad} failing")
    flagged = sum(1 for n in names if FORMAT_CONTROL_ISSUE in name_issues(n["name_issue"]))
    bad = sum(1 for n in names if has_format_controls(n["name"]) != (FORMAT_CONTROL_ISSUE in name_issues(n["name_issue"])))
    check("name rows with invisible format controls, and only those, carry name_issue format_control", bad == 0,
          f"{flagged} flagged; {bad} failing")
    has_ar = {n["record_id"] for n in names if n["is_arabic"]}
    check("every record has at least one Arabic name", has_ar == pid, f"{len(pid - has_ar)} without")
    bad = sum(1 for n in names if n["source_license"] not in ("CC-BY-4.0", "CC0-1.0"))
    check("every name carries its source licence", bad == 0)
    bad = sum(1 for n in names if not n["cluster_id"].startswith(n["record_id"] + "~"))
    check("clusters never span two records", bad == 0)

    ug = [u["geoname_id"] for u in units]
    check("admin unit IDs unique", len(ug) == len(set(ug)))
    uset = set(ug)
    bad = sum(1 for u in units if u["level"] > 0 and u["parent_geoname_id"] is not None
              and u["parent_geoname_id"] not in uset)
    none = sum(1 for u in units if u["level"] > 0 and u["parent_geoname_id"] is None)
    check("every known admin parent is in the table", bad == 0,
          f"{bad} failing; {none} units whose parent code does not resolve in GeoNames")

    exid = [e["example_id"] for e in ex]
    check("example_id unique", len(exid) == len(set(exid)), f"{len(exid)} examples")
    bad = sum(1 for e in ex if e["target_record_id"] not in pid)
    check("every match target exists", bad == 0)
    bad = sum(1 for e in ex if e["target_record_id"] in e["distractor_ids"]
              or any(d not in pid for d in e["distractor_ids"]))
    check("distractors exist and differ from the target", bad == 0)
    split_of = {}
    overlap = 0
    for e in ex:
        s = split_of.setdefault(e["target_record_id"], e["split"])
        overlap += int(s != e["split"])
    check("no target in more than one split", overlap == 0)
    share = sum(1 for e in ex if e["n_distractors"] >= 2) / len(ex) if ex else 0
    check(f"at least {min_distractor_share:.0%} of examples have two or more same-name distractors",
          share >= min_distractor_share, f"{share:.1%}")
    check(f"at least {min_examples:,} match examples", len(ex) >= min_examples, f"{len(ex)}")
    return out


def write(release: str, **limits) -> list:
    res = run(release, **limits)
    os.makedirs(os.path.join(release, "meta"), exist_ok=True)
    with open(os.path.join(release, "meta", "validation.json"), "w", encoding="utf-8") as fh:
        json.dump({"passed": all(ok for _, ok, _ in res), "n_checks": len(res),
                   "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in res]},
                  fh, ensure_ascii=False, indent=1)
    return res

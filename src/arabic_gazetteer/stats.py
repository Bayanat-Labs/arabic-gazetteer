"""Counts for the card and the website, computed from the released files only, and the coverage
chart."""
from __future__ import annotations

import csv
import glob
import json
import os
import statistics
from collections import Counter, defaultdict

from .config import STATE_NAMES_EN, STATES
from .textnorm import FORMAT_CONTROL_ISSUE, name_issues, visible


def _read(release: str, config: str, columns=None) -> list[dict]:
    import pyarrow.parquet as pq

    files = sorted(glob.glob(os.path.join(release, "data", config, "*.parquet")))
    rows = []
    for f in files:
        rows += pq.read_table(f, columns=columns).to_pylist()
    return rows


def read_coverage(release: str) -> list[dict]:
    with open(os.path.join(release, "meta", "state_coverage.csv"), encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in list(r):
            if k not in ("country_code", "state"):
                r[k] = int(r[k])
    return rows


def compute(release: str) -> dict:
    places = _read(release, "places", ["record_id", "source", "country_code", "feature_class",
                                       "admin_levels", "admin_levels_resolved", "hierarchy_check",
                                       "admin_path",
                                       "possible_duplicate_of", "name_ar_rule", "wikidata_links",
                                       "latitude", "longitude", "population"])
    names = _read(release, "names", ["record_id", "name", "script", "lang", "is_arabic", "is_latin",
                                     "source", "cluster_id", "name_issue", "historic", "preferred",
                                     "colloquial", "short"])
    units = _read(release, "admin_units", ["level", "country_code", "name_ar", "parent_geoname_id"])
    ex = _read(release, "match_examples", ["target_record_id", "split", "input_kind",
                                           "label_origin", "n_distractors", "input_script"])
    cc_of = {p["record_id"]: p["country_code"] for p in places}
    st = {}
    st["places"] = len(places)
    st["places_by_source"] = dict(Counter(p["source"] for p in places))
    st["places_by_feature_class"] = dict(Counter(p["feature_class"] for p in places).most_common())
    st["canonical_ar_rule"] = dict(Counter(p["name_ar_rule"] for p in places).most_common())
    st["hierarchy_check"] = dict(Counter(p["hierarchy_check"] for p in places).most_common())
    st["possible_duplicates"] = sum(1 for p in places if p["possible_duplicate_of"])
    st["places_with_population"] = sum(1 for p in places if p["population"])
    full = sum(1 for p in places if p["admin_levels"] == p["admin_levels_resolved"])
    st["admin_path_fully_resolved"] = full
    st["admin_path_fully_resolved_share"] = round(full / len(places), 4)
    lv = Counter()
    for p in places:
        lv["levels"] += p["admin_levels"]
        lv["resolved"] += p["admin_levels_resolved"]
    by_level = Counter()
    for p in places:
        for n in p["admin_path"][1:]:
            by_level[(n["level"], "records")] += 1
            by_level[(n["level"], "resolved")] += int(n["status"] == "resolved")
    st["admin_level_resolution"] = {
        str(lvl): {"records_with_level": by_level[(lvl, "records")], "resolved": by_level[(lvl, "resolved")],
                   "share": round(by_level[(lvl, "resolved")] / by_level[(lvl, "records")], 4)}
        for lvl in sorted({k[0] for k in by_level})}
    st["admin_levels_resolved_share"] = round(lv["resolved"] / lv["levels"], 4) if lv["levels"] else None
    links = Counter()
    for p in places:
        for l in p["wikidata_links"] or []:
            links[l["status"] if l["status"] == "accepted" else f"rejected_{l['reason']}"] += 1
    st["geonames_wikidata_links"] = dict(links)

    st["name_rows"] = len(names)
    for n in names:  # distinct names are counted by their visible form (no format controls)
        n["name"] = visible(n["name"])
    ar = [n for n in names if n["is_arabic"]]
    la = [n for n in names if n["is_latin"]]
    st["arabic_name_rows"] = len(ar)
    st["latin_name_rows"] = len(la)
    st["arabic_names_distinct_per_place"] = len({(n["record_id"], n["name"]) for n in ar})
    st["latin_names_distinct_per_place"] = len({(n["record_id"], n["name"]) for n in la})
    st["arabic_name_strings_distinct"] = len({n["name"] for n in ar})
    st["name_rows_by_source"] = dict(Counter(n["source"] for n in names))
    st["name_rows_by_script"] = dict(Counter(n["script"] for n in names))
    st["name_issues"] = dict(Counter(i for n in names for i in name_issues(n["name_issue"])).most_common())
    st["name_rows_with_two_issues"] = sum(1 for n in names if len(name_issues(n["name_issue"])) > 1)
    st["format_control_rows_by_script"] = dict(Counter(
        n["script"] for n in names if FORMAT_CONTROL_ISSUE in name_issues(n["name_issue"])).most_common())
    st["untyped_arabic_script_rows"] = sum(1 for n in names if n["script"] == "Arab" and n["lang"] is None)
    st["flags"] = {k: sum(1 for n in names if n[k]) for k in ("preferred", "short", "colloquial", "historic")}
    for label, rows in (("arabic", ar), ("latin", la)):
        size = Counter(n["cluster_id"] for n in rows)
        distinct = defaultdict(set)
        for n in rows:
            distinct[n["cluster_id"]].add(n["name"])
        sizes = [len(v) for v in distinct.values()]
        st[f"{label}_clusters"] = len(size)
        st[f"{label}_cluster_distinct_names_mean"] = round(statistics.mean(sizes), 3) if sizes else None
        st[f"{label}_cluster_distinct_names_median"] = statistics.median(sizes) if sizes else None
        st[f"{label}_cluster_distinct_names_max"] = max(sizes) if sizes else None
        st[f"{label}_clusters_with_2plus_spellings"] = sum(1 for s in sizes if s >= 2)
    per_place_ar = Counter()
    for n in {(n["record_id"], n["cluster_id"]) for n in ar}:
        per_place_ar[n[0]] += 1
    st["places_with_2plus_arabic_clusters"] = sum(1 for v in per_place_ar.values() if v >= 2)
    per_place_la = Counter()
    for n in {(n["record_id"], n["cluster_id"]) for n in la}:
        per_place_la[n[0]] += 1
    st["places_with_latin_names"] = len(per_place_la)
    st["places_with_2plus_latin_clusters"] = sum(1 for v in per_place_la.values() if v >= 2)

    st["admin_units"] = len(units)
    st["admin_units_by_level"] = {str(k): v for k, v in sorted(Counter(u["level"] for u in units).items())}
    st["admin_units_with_name_ar"] = sum(1 for u in units if u["name_ar"])
    st["admin_units_parent_unresolved"] = sum(1 for u in units if u["level"] > 0 and u["parent_geoname_id"] is None)

    st["match_examples"] = len(ex)
    st["match_examples_by_split"] = dict(Counter(e["split"] for e in ex))
    st["match_examples_by_kind"] = dict(Counter(e["input_kind"] for e in ex).most_common())
    st["match_examples_by_origin"] = dict(Counter(e["label_origin"] for e in ex))
    st["match_examples_by_script"] = dict(Counter(e["input_script"] for e in ex))
    st["match_targets"] = len({e["target_record_id"] for e in ex})
    st["match_examples_2plus_distractors"] = sum(1 for e in ex if e["n_distractors"] >= 2)
    st["match_examples_2plus_distractors_share"] = round(st["match_examples_2plus_distractors"] / len(ex), 4) if ex else None

    per = {}
    for cc in STATES:
        per[cc] = Counter()
    for p in places:
        c = per[p["country_code"]]
        c["places"] += 1
        c[f"source_{p['source']}"] += 1
        c["admin_full"] += int(p["admin_levels"] == p["admin_levels_resolved"])
    for n in ar:
        per[cc_of[n["record_id"]]]["arabic_name_rows"] += 1
    for n in la:
        per[cc_of[n["record_id"]]]["latin_name_rows"] += 1
    for cid in {(n["record_id"], n["cluster_id"]) for n in ar}:
        per[cc_of[cid[0]]]["arabic_clusters"] += 1
    for e in ex:
        per[cc_of[e["target_record_id"]]]["match_examples"] += 1
    cov = {r["country_code"]: r for r in read_coverage(release)}
    st["per_state"] = []
    for cc in sorted(STATES, key=lambda c: -per[c]["places"]):
        c = per[cc]
        r = cov.get(cc, {})
        st["per_state"].append({
            "country_code": cc, "state": STATE_NAMES_EN[cc], "places": c["places"],
            "geonames_only": c["source_geonames"], "geonames_and_wikidata": c["source_geonames+wikidata"],
            "wikidata_only": c["source_wikidata"], "arabic_name_rows": c["arabic_name_rows"],
            "latin_name_rows": c["latin_name_rows"], "arabic_clusters": c["arabic_clusters"],
            "admin_path_fully_resolved_share": round(c["admin_full"] / c["places"], 4) if c["places"] else None,
            "match_examples": c["match_examples"],
            "geonames_features_in_scope": r.get("geonames_features_in_scope"),
            "geonames_features_with_arabic_name": r.get("with_arabic_name_any"),
            "geonames_features_with_arabic_name_in_geonames": r.get("with_arabic_name_geonames"),
            "arabic_name_coverage": round(r["with_arabic_name_any"] / r["geonames_features_in_scope"], 4)
            if r.get("geonames_features_in_scope") else None,
        })
    tot_scope = sum(r["geonames_features_in_scope"] for r in cov.values())
    tot_ar = sum(r["with_arabic_name_any"] for r in cov.values())
    tot_ar_gn = sum(r["with_arabic_name_geonames"] for r in cov.values())
    st["geonames_features_in_scope"] = tot_scope
    st["geonames_features_with_arabic_name"] = tot_ar
    st["geonames_features_with_arabic_name_in_geonames"] = tot_ar_gn
    st["geonames_features_arabic_name_from_wikidata_only"] = tot_ar - tot_ar_gn
    st["arabic_name_coverage_all"] = round(tot_ar / tot_scope, 4) if tot_scope else None
    return st


def chart(stats: dict, out_png: str, out_svg: str | None = None) -> None:
    """Horizontal bars: share of GeoNames features in scope that have an Arabic name, per state."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in stats["per_state"] if r["arabic_name_coverage"] is not None]
    rows.sort(key=lambda r: r["arabic_name_coverage"])
    surface, ink, ink2, bar, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#e4e3df"
    fig, ax = plt.subplots(figsize=(9, 7.2), dpi=150)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    y = range(len(rows))
    vals = [r["arabic_name_coverage"] * 100 for r in rows]
    ax.barh(list(y), vals, height=0.62, color=bar, zorder=2)
    for i, (r, v) in enumerate(zip(rows, vals)):
        ax.text(v + 1, i, f"{v:.1f}%  ({r['geonames_features_with_arabic_name']:,} of {r['geonames_features_in_scope']:,})",
                va="center", ha="left", fontsize=8.5, color=ink2)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r["state"] for r in rows], fontsize=9, color=ink)
    ax.set_xlim(0, 130)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=8.5, color=ink2)
    ax.grid(axis="x", color=grid, linewidth=0.8, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(grid)
    ax.tick_params(axis="both", length=0)
    ax.set_title("GeoNames features with at least one Arabic name, by state",
                 loc="left", fontsize=12, color=ink, pad=14)
    fig.text(0.01, 0.01, "Features in the gazetteer's feature classes; an Arabic name from GeoNames or from the linked "
             "Wikidata item counts. Data: GeoNames (CC BY 4.0), Wikidata (CC0).", fontsize=7.5, color=ink2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_png, facecolor=surface)
    if out_svg:
        fig.savefig(out_svg, facecolor=surface, metadata={"Date": None})
    plt.close(fig)


def write(release: str) -> dict:
    st = compute(release)
    os.makedirs(os.path.join(release, "meta"), exist_ok=True)
    with open(os.path.join(release, "meta", "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is not installed: chart not drawn (pip install matplotlib)")
        return st
    os.makedirs(os.path.join(release, "images"), exist_ok=True)
    chart(st, os.path.join(release, "images", "arabic_name_coverage.png"))
    return st

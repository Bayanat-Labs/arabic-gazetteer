"""Build the gazetteer tables: places, names and admin_units."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict

from .config import (ARABIC_LANGS, CODE_PSEUDO_LANGS, KEEP_CLASSES, KEEP_S_CODES,
                     LARGE_PLACE_POPULATION, LINK_MAX_KM, LINK_MAX_KM_LARGE_PLACE,
                     LINK_PSEUDO_LANG, QID_TO_STATE, STATE_NAMES_AR, STATE_NAMES_EN, STATES,
                     WD_ARABIC_LANGS, WD_LATIN_LANGS, WD_NAME_PROPS, WIKIDATA_PSEUDO_LANG)
from .textnorm import (ar_match_key, ar_norm, clean, latin_fold, latin_match_key, name_issue,
                       script_issue, script_of, visible)
from .wikidata import item_family

ADM_LEVEL = {"ADM1": 1, "ADM2": 2, "ADM3": 3, "ADM4": 4, "ADM5": 5}
LICENSE_GN = "CC-BY-4.0"
LICENSE_WD = "CC0-1.0"


def _h(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def in_scope(f) -> bool:
    return f.cc in STATES and (f.fclass in KEEP_CLASSES or (f.fclass == "S" and f.fcode in KEEP_S_CODES))


def gn_record_id(gid: int) -> str:
    return f"bl-gaz-gn-{gid}"


def wd_record_id(qid: str) -> str:
    return f"bl-gaz-wd-{qid}"


# --- links ----------------------------------------------------------------------------------

def link_candidates(gn, items) -> dict:
    """(geonameid, qid) -> set of methods ('p1566', 'wkdt')."""
    cands: dict = defaultdict(set)
    for qid, it in items.items():
        for gid in it.p1566:
            if gid in gn.features:
                cands[(gid, qid)].add("p1566")
    for gid, alts in gn.alternates.items():
        for a in alts:
            if a.lang == WIKIDATA_PSEUDO_LANG and a.name.startswith("Q") and a.name[1:].isdigit():
                cands[(gid, a.name)].add("wkdt")
    return cands


def evaluate_links(gn, items, cands) -> dict:
    """geonameid -> list of link dicts (accepted first, best first)."""
    by_gid: dict = defaultdict(list)
    for (gid, qid), methods in cands.items():
        f = gn.features[gid]
        it = items.get(qid)
        method = "+".join(sorted(methods, key=lambda m: m != "p1566"))
        link = {"qid": qid, "method": method, "distance_km": None, "status": "accepted", "reason": None}
        if it is None:
            link["status"], link["reason"] = "rejected", "item_not_in_slice"
        else:
            if it.lat is not None and it.lon is not None:
                d = haversine_km(f.lat, f.lon, it.lat, it.lon)
                link["distance_km"] = round(d, 3)
                limit = LINK_MAX_KM.get(f.fclass, 10.0)
                if f.fclass == "P" and (f.population or 0) >= LARGE_PLACE_POPULATION:
                    limit = LINK_MAX_KM_LARGE_PLACE
                if d > limit:
                    link["status"], link["reason"] = "rejected", "distance"
            else:
                link["reason"] = "no_wikidata_coordinates"
        by_gid[gid].append(link)
    for gid, links in by_gid.items():
        # accepted first; then a link stated on both sides; then the item with more sitelinks;
        # then the shorter distance
        links.sort(key=lambda l: (l["status"] != "accepted", "+" not in l["method"],
                                  -(items[l["qid"]].n_sitelinks if l["qid"] in items else 0),
                                  l["distance_km"] if l["distance_km"] is not None else 1e9,
                                  int(l["qid"][1:])))
    return by_gid


# --- names ----------------------------------------------------------------------------------

def _name_row(record_id, name, lang, source, field, source_id, slot, preferred=False, short=False,
              colloquial=False, historic=False, valid_from=None, valid_to=None):
    # `name` keeps the source string (NFC, spaces collapsed); script, keys and the canonical names
    # use its visible form, without invisible format controls
    name = clean(name)
    shown = visible(name)
    if not shown:
        return None
    sc = script_of(shown)
    issue = name_issue(name, sc, slot)
    is_ar = slot == "ar" and sc == "Arab"
    is_lat = slot == "latin" and sc == "Latn"
    if sc == "Arab":
        key, mkey, fam = ar_norm(shown), ar_match_key(shown), "nf-ar-"
    else:
        key, mkey, fam = latin_fold(shown), latin_match_key(shown), "nf-la-"
    if not key:
        return None
    lic = LICENSE_GN if source == "geonames" else LICENSE_WD
    return {
        "record_id": record_id, "name": name, "script": sc, "lang": lang, "is_arabic": is_ar,
        "is_latin": is_lat, "source": source, "source_field": field, "source_name_id": source_id,
        "preferred": preferred, "short": short, "colloquial": colloquial, "historic": historic,
        "valid_from": valid_from, "valid_to": valid_to, "name_norm": key, "match_key": mkey,
        "cluster_id": f"{record_id}~{'ar' if sc == 'Arab' else 'la'}~{_h(key, 10)}",
        "name_family_id": fam + _h(mkey) if mkey else None, "name_issue": issue,
        "is_canonical_ar": False, "source_license": lic,
    }


def geonames_names(record_id, f, alts) -> tuple[list, list, list]:
    """Name rows, codes and Wikipedia links of one GeoNames feature."""
    rows, codes, links = [], [], []
    main_slot = "ar" if script_of(f.name) == "Arab" else "latin"
    r = _name_row(record_id, f.name, None, "geonames", "name", f"gn-{f.geonameid}-name", main_slot)
    if r:
        r["is_arabic"] = False  # the main name has no language tag
        rows.append(r)
    if f.asciiname and f.asciiname != f.name:
        r = _name_row(record_id, f.asciiname, None, "geonames", "asciiname", f"gn-{f.geonameid}-ascii", "latin")
        if r:
            rows.append(r)
    for a in sorted(alts, key=lambda x: x.alt_id):
        if a.lang in CODE_PSEUDO_LANGS:
            codes.append({"type": CODE_PSEUDO_LANGS[a.lang], "value": a.name})
            continue
        if a.lang == LINK_PSEUDO_LANG:
            links.append(a.name)
            continue
        if a.lang == WIKIDATA_PSEUDO_LANG:
            continue
        if a.lang in ARABIC_LANGS:
            slot = "ar"
        elif a.lang in ("en", "fr"):
            slot = "latin"
        elif a.lang is None:
            sc = script_of(a.name)
            if sc == "Arab":
                slot = "ar_untyped"
            elif sc == "Latn":
                slot = "latin"
            else:
                continue
        else:
            continue
        r = _name_row(record_id, a.name, a.lang, "geonames", "alternate_name", f"gn-alt-{a.alt_id}",
                      "ar" if slot == "ar_untyped" else slot, a.preferred, a.short, a.colloquial,
                      a.historic, a.valid_from, a.valid_to)
        if r:
            if slot == "ar_untyped":
                r["is_arabic"] = False
            rows.append(r)
    return rows, codes, links


def wikidata_names(record_id, it) -> list:
    rows = []
    for lang in WD_ARABIC_LANGS + WD_LATIN_LANGS:
        slot = "ar" if lang in WD_ARABIC_LANGS else "latin"
        if lang in it.labels:
            r = _name_row(record_id, it.labels[lang], lang, "wikidata", "label", f"wd-{it.qid}-{lang}-label", slot)
            if r:
                rows.append(r)
        for i, al in enumerate(it.aliases.get(lang, [])):
            r = _name_row(record_id, al, lang, "wikidata", "alias", f"wd-{it.qid}-{lang}-alias-{i}", slot)
            if r:
                rows.append(r)
    for i, (pid, lang, value) in enumerate(it.names):
        slot = "ar" if lang in WD_ARABIC_LANGS else "latin"
        r = _name_row(record_id, value, lang, "wikidata", WD_NAME_PROPS[pid], f"wd-{it.qid}-{pid}-{i}", slot,
                      short=(pid == "P1813"))
        if r:
            rows.append(r)
    return rows


def has_arabic_name(rows) -> bool:
    return any(r["is_arabic"] for r in rows)


def choose_canonical_ar(rows) -> tuple[dict | None, str | None]:
    """Canonical Arabic name: (1) a GeoNames Arabic name marked preferred (not historic, not
    colloquial), lowest alternate-name ID first; (2) the Wikidata Arabic label (ar, then arz,
    ary); (3) the GeoNames Arabic name whose cluster key is most frequent (not historic), lowest
    ID first; (4) any other Arabic name from Wikidata. Names with a script issue are skipped.
    Invisible format controls do not count against a name: the caller takes the visible form of
    the chosen row as the canonical name."""
    ar = [r for r in rows if r["is_arabic"] and script_issue(r["name_issue"]) in (None, "extended_letters")]
    clean_ar = [r for r in ar if script_issue(r["name_issue"]) is None] or ar

    def gn_id(r):
        sid = r["source_name_id"]
        return int(sid.rsplit("-", 1)[1]) if sid.startswith("gn-alt-") else 0

    gn = [r for r in clean_ar if r["source"] == "geonames"]
    pref = [r for r in gn if r["preferred"] and not r["historic"] and not r["colloquial"]]
    if pref:
        return min(pref, key=gn_id), "geonames_preferred"
    for lang in WD_ARABIC_LANGS:
        for r in clean_ar:
            if r["source"] == "wikidata" and r["source_field"] == "label" and r["lang"] == lang:
                return r, "wikidata_label"
    cur = [r for r in gn if not r["historic"]] or gn
    if cur:
        freq = Counter(r["name_norm"] for r in cur)
        return min(cur, key=lambda r: (-freq[r["name_norm"]], gn_id(r))), "geonames_most_frequent"
    wd = [r for r in clean_ar if r["source"] == "wikidata"]
    if wd:
        return wd[0], "wikidata_other"
    return None, None


def choose_name_en(rows, f=None):
    """English or Latin display name: a GeoNames English name marked preferred, then the Wikidata
    English label, then another GeoNames English name, then the GeoNames main name, then the
    Wikidata French label. The name is returned without invisible format controls."""
    def pick(cond):
        for r in rows:
            if cond(r):
                return r
        return None
    for cond, why in (
        (lambda r: r["source"] == "geonames" and r["lang"] == "en" and r["preferred"] and not r["historic"] and r["is_latin"], "geonames_en_preferred"),
        (lambda r: r["source"] == "wikidata" and r["lang"] == "en" and r["source_field"] == "label" and r["is_latin"], "wikidata_en_label"),
        (lambda r: r["source"] == "geonames" and r["lang"] == "en" and not r["historic"] and r["is_latin"], "geonames_en"),
        (lambda r: r["source"] == "geonames" and r["source_field"] == "name" and r["script"] == "Latn", "geonames_name"),
        (lambda r: r["source"] == "wikidata" and r["lang"] == "fr" and r["source_field"] == "label" and r["is_latin"], "wikidata_fr_label"),
    ):
        r = pick(cond)
        if r:
            return visible(r["name"]), why
    return None, None


# --- admin hierarchy ------------------------------------------------------------------------

class Admin:
    """Admin units from the GeoNames admin codes and ADM1-ADM4 features."""

    def __init__(self, gn):
        self.gn = gn
        self.unit = {}       # (cc, level, codes tuple) -> geonameid
        for gid, f in gn.features.items():
            lvl = ADM_LEVEL.get(f.fcode)
            if lvl and lvl <= 4:
                codes = tuple(f.admin[:lvl])
                if all(c and c != "00" for c in codes):
                    self.unit.setdefault((f.cc, lvl, codes), gid)
        for code, (_, _, gid) in gn.admin1.items():
            cc, a1 = code.split(".", 1)
            if gid:
                self.unit[(cc, 1, (a1,))] = gid
        for code, (_, _, gid) in gn.admin2.items():
            parts = code.split(".")
            if len(parts) == 3 and gid:
                self.unit[(parts[0], 2, (parts[1], parts[2]))] = gid
        self.max_level = {}
        for cc in STATES:
            m = 0
            for lvl in (1, 2, 3, 4):
                if any(k[0] == cc and k[1] == lvl for k in self.unit):
                    m = lvl
            self.max_level[cc] = m
        self.unit_level = {gid: k[1] for k, gid in self.unit.items()}
        self.unit_code = {gid: f"{k[0]}." + ".".join(k[2]) for k, gid in self.unit.items()}

    def path(self, f):
        """[(level, code, geonameid or None)] from level 1 to the country's deepest level, or to
        the level above the feature's own level for an admin unit."""
        own = ADM_LEVEL.get(f.fcode)
        top = self.max_level.get(f.cc, 0)
        if own:
            top = min(top, own - 1)
        elif f.fcode.startswith("PCL"):
            top = 0  # the country itself
        out = []
        for lvl in range(1, top + 1):
            codes = tuple(f.admin[:lvl])
            ok = all(c and c != "00" for c in codes)
            gid = self.unit.get((f.cc, lvl, codes)) if ok else None
            out.append((lvl, f"{f.cc}." + ".".join(codes) if ok else None, gid))
        return out

    def path_of_unit(self, gid):
        f = self.gn.features.get(gid)
        if f is None:
            return []
        lvl = self.unit_level.get(gid)
        own = self.path(f)
        if lvl:
            own = own[: lvl - 1] + [(lvl, self.unit_code.get(gid), gid)]
        return own


# --- main build -----------------------------------------------------------------------------

def build(gn, items, class_map, gn_version: str, wd_version: str, log=print) -> dict:
    """Return {'places': [...], 'names': [...], 'admin_units': [...], 'links': [...], 'stats': {...}}."""
    admin = Admin(gn)
    cands = link_candidates(gn, items)
    links_by_gid = evaluate_links(gn, items, cands)
    stats = Counter()

    # GeoNames records
    coverage = {cc: Counter() for cc in STATES}
    recs, names_by_rec = {}, {}
    primary_qid_of = {}
    for gid in sorted(gn.features):
        f = gn.features[gid]
        if not in_scope(f):
            continue
        rid = gn_record_id(gid)
        rows, codes, wlinks = geonames_names(rid, f, gn.alternates.get(gid, []))
        coverage[f.cc]["geonames_features_in_scope"] += 1
        coverage[f.cc]["with_arabic_name_geonames"] += int(has_arabic_name(rows))
        links = links_by_gid.get(gid, [])
        acc = [l for l in links if l["status"] == "accepted"]
        it = items.get(acc[0]["qid"]) if acc else None
        if it is not None:
            rows += wikidata_names(rid, it)
        if not has_arabic_name(rows):
            continue
        coverage[f.cc]["with_arabic_name_any"] += 1
        recs[rid] = {"kind": "gn", "gid": gid, "f": f, "item": it, "links": links,
                     "codes": codes, "wikipedia_links": wlinks}
        names_by_rec[rid] = rows
        if it is not None:
            primary_qid_of.setdefault(it.qid, []).append(rid)

    # items linked (as first or further link) to a GeoNames feature in scope are not
    # Wikidata-only places
    linked_qids = set(primary_qid_of)
    for gid, links in links_by_gid.items():
        if in_scope(gn.features[gid]):
            linked_qids |= {l["qid"] for l in links if l["status"] == "accepted"}
    # Wikidata-only records
    for qid in sorted(items, key=lambda q: int(q[1:])):
        it = items[qid]
        if qid in linked_qids or it.class_group != "place" or it.lat is None or it.lon is None:
            continue
        if not it.p17_states:
            continue
        if not any(l in it.labels for l in WD_ARABIC_LANGS):
            continue
        fam = item_family(it, class_map)
        if fam in ("X", "-"):
            stats[f"wd_only_skipped_family_{fam}"] += 1
            continue
        rid = wd_record_id(qid)
        rows = wikidata_names(rid, it)
        if not has_arabic_name(rows):
            continue
        coverage[it.p17_states[0]]["wikidata_only_records"] += 1
        recs[rid] = {"kind": "wd", "item": it, "family": fam, "links": [], "codes": [], "wikipedia_links": []}
        names_by_rec[rid] = rows

    # canonical names first (admin paths need them)
    canon = {}
    for rid, rows in names_by_rec.items():
        c, rule = choose_canonical_ar(rows)
        c["is_canonical_ar"] = True
        en, en_rule = choose_name_en(rows)
        canon[rid] = (c, rule, en, en_rule)

    rec_of_gid = {r["gid"]: rid for rid, r in recs.items() if r["kind"] == "gn"}
    # QID -> GeoNames record (for P131 walks): records whose primary link is the QID
    gid_of_qid = {}
    for qid, rids in primary_qid_of.items():
        gids = sorted(recs[r]["gid"] for r in rids)
        # prefer an admin unit, then a populated place
        gids.sort(key=lambda g: (gn.features[g].fcode not in ADM_LEVEL, gn.features[g].fclass != "P", g))
        gid_of_qid[qid] = gids[0]

    def unit_names(gid):
        rid = rec_of_gid.get(gid)
        if rid:
            return visible(canon[rid][0]["name"]), canon[rid][2]
        f = gn.features.get(gid)
        if f is None:
            return None, None
        best_ar = None
        for a in sorted(gn.alternates.get(gid, []), key=lambda x: (not x.preferred, x.alt_id)):
            if a.lang in ARABIC_LANGS and script_of(a.name) == "Arab" and visible(a.name):
                best_ar = visible(a.name)
                break
        return best_ar, visible(f.name) or f.name

    def node(level, code, gid, source):
        if gid is None:
            return {"level": level, "code": code, "geoname_id": None, "record_id": None,
                    "name_ar": None, "name_en": None, "status": "unresolved", "source": source}
        nar, nen = unit_names(gid)
        return {"level": level, "code": code, "geoname_id": gid, "record_id": rec_of_gid.get(gid),
                "name_ar": nar, "name_en": nen, "status": "resolved", "source": source}

    def country_node(cc):
        name, gid = gn.countries.get(cc, (STATE_NAMES_EN[cc], None))
        nd = node(0, cc, gid, "geonames_country") if gid else {
            "level": 0, "code": cc, "geoname_id": None, "record_id": None, "name_ar": STATE_NAMES_AR[cc],
            "name_en": STATE_NAMES_EN[cc], "status": "resolved", "source": "country_code"}
        return nd

    # non-admin parents from the GeoNames hierarchy (for example a district within a city)
    parents = defaultdict(list)
    for p, ch, typ in gn.hierarchy:
        if typ == "ADM":
            continue
        pf, cf = gn.features.get(p), gn.features.get(ch)
        if pf and cf and pf.fclass == "P" and pf.cc == cf.cc and p != ch:
            parents[ch].append(p)

    def gn_path(gid):
        f = gn.features[gid]
        return [country_node(f.cc)] + [node(l, c, g, "geonames_admin_codes") for l, c, g in admin.path(f)]

    def p131_linked(qid, cc, max_steps=12):
        """First GeoNames features reached by walking P131 up from the item (same country)."""
        found, seen, frontier = [], {qid}, list(items[qid].p131) if qid in items else []
        steps = 0
        while frontier and steps < max_steps:
            nxt = []
            for q in frontier:
                if q in seen:
                    continue
                seen.add(q)
                g = gid_of_qid.get(q)
                if g is not None and gn.features[g].cc == cc and gn.features[g].fcode not in ("PCLI", "PCLD", "PCLIX", "PCLS", "PCLF", "PCL", "TERR"):
                    found.append(g)
                    continue
                if q in items:
                    nxt.extend(items[q].p131)
            if found:
                break
            frontier = nxt
            steps += 1
        return found

    places, names = [], []
    for rid in sorted(recs, key=lambda r: (recs[r]["kind"] != "gn", recs[r].get("gid") or 0, r)):
        r = recs[rid]
        rows = names_by_rec[rid]
        c, rule, en, en_rule = canon[rid]
        it = r["item"]
        if r["kind"] == "gn":
            f = r["f"]
            path = gn_path(r["gid"])
            path_source = "geonames_admin_codes"
            cc, lat, lon = f.cc, f.lat, f.lon
            other_cc = sorted({x for x in f.cc2 if x != f.cc})
            fclass, fcode, fclass_source = f.fclass, f.fcode, "geonames"
            pop, pop_src = (f.population, "geonames") if f.population else (
                (it.population, "wikidata") if it is not None and it.population else (None, None))
            parent_ids = sorted(set(parents.get(r["gid"], [])))
            check = "not_compared"
            if it is not None:
                found = [g for g in p131_linked(it.qid, cc) if g != r["gid"]]
                check = _hierarchy_check(found, r["gid"], admin, gn, parents)
            src = "geonames+wikidata" if it is not None else "geonames"
            refs = [{"source": "geonames", "source_record_id": str(r["gid"]),
                     "url": f"https://www.geonames.org/{r['gid']}", "version": gn_version}]
            modified = f.modified
            gname = f.name
        else:
            cc = it.p17_states[0]
            other_cc = sorted(set(it.p17_states[1:]))
            lat, lon = it.lat, it.lon
            fclass, fcode, fclass_source = r["family"], None, "wikidata_class_map"
            pop, pop_src = (it.population, "wikidata") if it.population else (None, None)
            parent_ids = []
            found = p131_linked(it.qid, cc)
            path = [country_node(cc)]
            path_source = "country_only"
            top = admin.max_level.get(cc, 0)
            if found:
                g = found[0]
                gf = gn.features[g]
                base = admin.path_of_unit(g) if g in admin.unit_level else admin.path(gf)
                if gf.fcode not in ADM_LEVEL and gf.fclass == "P":
                    parent_ids = [g]
                got = {l: (c2, g2) for l, c2, g2 in base}
                for lvl in range(1, top + 1):
                    c2, g2 = got.get(lvl, (None, None))
                    path.append(node(lvl, c2, g2, "wikidata_p131_to_geonames") if g2 else node(lvl, None, None, "wikidata_p131_to_geonames"))
                path_source = "wikidata_p131_to_geonames"
            else:
                for lvl in range(1, top + 1):
                    path.append(node(lvl, None, None, "none"))
            check = "not_compared"
            src = "wikidata"
            refs = []
            modified = None
            gname = None
        if it is not None:
            refs.append({"source": "wikidata", "source_record_id": it.qid,
                         "url": f"https://www.wikidata.org/wiki/{it.qid}", "version": wd_version})
        ar_rows = [x for x in rows if x["is_arabic"]]
        la_rows = [x for x in rows if x["is_latin"]]
        resolved = sum(1 for n in path[1:] if n["status"] == "resolved")
        places.append({
            "record_id": rid, "source": src,
            "geoname_id": r.get("gid"), "wikidata_qid": it.qid if it is not None else None,
            "wikidata_links": r["links"],
            "name_ar": visible(c["name"]), "name_ar_norm": c["name_norm"], "name_ar_rule": rule,
            "name_en": en, "name_en_rule": en_rule, "geonames_name": gname,
            "names_ar": sorted({visible(x["name"]) for x in ar_rows}),
            "names_latin": sorted({visible(x["name"]) for x in la_rows}),
            "n_names_ar": len({visible(x["name"]) for x in ar_rows}),
            "n_names_latin": len({visible(x["name"]) for x in la_rows}),
            "n_clusters_ar": len({x["cluster_id"] for x in ar_rows}),
            "n_clusters_latin": len({x["cluster_id"] for x in la_rows}),
            "name_family_id": c["name_family_id"],
            "feature_class": fclass, "feature_code": fcode, "feature_class_source": fclass_source,
            "wikidata_classes": list(it.p31) if it is not None else [],
            "country_code": cc, "other_country_codes": other_cc,
            "latitude": lat, "longitude": lon,
            "coordinates_source": "geonames" if r["kind"] == "gn" else "wikidata",
            "population": pop, "population_source": pop_src,
            "admin_path": path, "admin_path_source": path_source,
            "admin_levels": len(path) - 1, "admin_levels_resolved": resolved,
            "parent_place_ids": [gn_record_id(g) if g in rec_of_gid else None for g in parent_ids if g in rec_of_gid],
            "hierarchy_check": check, "hierarchy_conflict": check == "disagree",
            "codes": r["codes"], "wikipedia_links": r["wikipedia_links"],
            "possible_duplicate_of": None,
            "geonames_modified": modified,
            "license_partition": "cc-by-4.0", "source_refs": refs,
            "label_origin": "deterministic_derivation", "review_status": "unreviewed",
        })
        names.extend(rows)

    _flag_duplicates(places)
    units = _admin_units(gn, admin, rec_of_gid, places, canon, unit_names)
    cov_rows = []
    for cc in STATES:
        c = coverage[cc]
        cov_rows.append({"country_code": cc, "state": STATE_NAMES_EN[cc],
                         "geonames_features_in_scope": c["geonames_features_in_scope"],
                         "with_arabic_name_geonames": c["with_arabic_name_geonames"],
                         "with_arabic_name_any": c["with_arabic_name_any"],
                         "wikidata_only_records": c["wikidata_only_records"]})
    stats["geonames_features_read"] = len(gn.features)
    stats["geonames_features_in_scope"] = sum(r["geonames_features_in_scope"] for r in cov_rows)
    stats["link_candidates"] = len(cands)
    return {"places": places, "names": names, "admin_units": units, "stats": dict(stats),
            "coverage": cov_rows}


def _levels(admin, gn, gid) -> dict:
    """level -> geonameid of the resolved admin units above (and, for an admin unit, at) gid."""
    f = gn.features[gid]
    path = admin.path_of_unit(gid) if gid in admin.unit_level else admin.path(f)
    return {lvl: g for lvl, _, g in path if g}


def _hierarchy_check(found, gid, admin, gn, parents) -> str:
    """Compare the GeoNames admin path of a record with the GeoNames features that its Wikidata
    item reaches through P131. 'agree': a reached feature is a GeoNames parent of the record, or
    its path matches the record's path at every level where both are resolved (at least one).
    'disagree': reached features exist and none of them agrees, and at least one is comparable.
    'not_compared' otherwise."""
    if not found:
        return "not_compared"
    own = _levels(admin, gn, gid)
    anc = set(own.values()) | set(parents.get(gid, []))
    compared = False
    for g in found:
        if g in anc:
            return "agree"
        other = _levels(admin, gn, g)
        common = [lvl for lvl in other if lvl in own]
        if not common:
            continue
        compared = True
        if all(other[lvl] == own[lvl] for lvl in common):
            return "agree"
    return "disagree" if compared else "not_compared"


def _flag_duplicates(places) -> None:
    """GeoNames records with the same country, feature code, Arabic key and coordinates (3
    decimals) point to the one with the lowest ID; a Wikidata-only record points to a GeoNames
    record with the same Arabic matching key within 2 km."""
    groups = defaultdict(list)
    for p in places:
        if p["geoname_id"] is not None:
            k = (p["country_code"], p["feature_code"], ar_match_key(p["name_ar"]),
                 round(p["latitude"], 3), round(p["longitude"], 3))
            groups[k].append(p)
    for g in groups.values():
        if len(g) > 1:
            g.sort(key=lambda p: p["geoname_id"])
            for p in g[1:]:
                p["possible_duplicate_of"] = g[0]["record_id"]
    grid = defaultdict(list)
    for p in places:
        if p["geoname_id"] is not None:
            grid[(ar_match_key(p["name_ar"]), int(p["latitude"] * 20), int(p["longitude"] * 20))].append(p)
    for p in places:
        if p["geoname_id"] is not None:
            continue
        key = ar_match_key(p["name_ar"])
        cy, cx = int(p["latitude"] * 20), int(p["longitude"] * 20)
        best = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for q in grid.get((key, cy + dy, cx + dx), ()):
                    d = haversine_km(p["latitude"], p["longitude"], q["latitude"], q["longitude"])
                    if d <= 2.0 and (best is None or d < best[0]):
                        best = (d, q["record_id"])
        if best:
            p["possible_duplicate_of"] = best[1]


def _admin_units(gn, admin, rec_of_gid, places, canon, unit_names) -> list:
    count = Counter()
    for p in places:
        for n in p["admin_path"][1:]:
            if n["geoname_id"]:
                count[n["geoname_id"]] += 1
    rows = []
    for cc in STATES:
        name, gid = gn.countries.get(cc, (None, None))
        if gid:
            nar, nen = unit_names(gid)
            rows.append({"geoname_id": gid, "record_id": rec_of_gid.get(gid), "country_code": cc,
                         "level": 0, "code": cc, "feature_code": gn.features[gid].fcode if gid in gn.features else None,
                         "parent_geoname_id": None, "name_ar": nar, "name_en": STATE_NAMES_EN[cc],
                         "geonames_name": name, "n_places": sum(1 for p in places if p["country_code"] == cc),
                         "latitude": gn.features[gid].lat if gid in gn.features else None,
                         "longitude": gn.features[gid].lon if gid in gn.features else None})
    for (cc, lvl, codes), gid in sorted(admin.unit.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        f = gn.features.get(gid)
        parent = admin.unit.get((cc, lvl - 1, codes[:-1])) if lvl > 1 else gn.countries.get(cc, (None, None))[1]
        nar, nen = unit_names(gid)
        src_name = (gn.admin1.get(f"{cc}." + ".".join(codes)) if lvl == 1 else
                    gn.admin2.get(f"{cc}." + ".".join(codes)) if lvl == 2 else None)
        rows.append({"geoname_id": gid, "record_id": rec_of_gid.get(gid), "country_code": cc, "level": lvl,
                     "code": f"{cc}." + ".".join(codes), "feature_code": f.fcode if f else None,
                     "parent_geoname_id": parent, "name_ar": nar,
                     "name_en": (canon[rec_of_gid[gid]][2] if gid in rec_of_gid else
                                 visible(src_name[0] if src_name else (f.name if f else "")) or None),
                     "geonames_name": src_name[0] if src_name else (f.name if f else None),
                     "n_places": count.get(gid, 0),
                     "latitude": f.lat if f else None, "longitude": f.lon if f else None})
    return rows

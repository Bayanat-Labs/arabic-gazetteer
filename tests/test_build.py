from arabic_gazetteer import geonames
from arabic_gazetteer.build import haversine_km


def _places(built):
    return {p["record_id"]: p for p in built["places"]}


def _names(built, rid):
    return [n for n in built["names"] if n["record_id"] == rid]


def test_read_geonames(geonames_dir):
    gn = geonames.read(geonames_dir, ["SA"])
    assert len(gn.features) == 12
    assert gn.admin1["SA.14"][2] == 104514
    assert gn.countries["SA"] == ("Saudi Arabia", 102358)
    assert any(a.lang == "iata" for a in gn.alternates[105343])
    assert (105343, 900010, "") in gn.hierarchy


def test_scope_and_arabic_name_rule(built):
    p = _places(built)
    assert "bl-gaz-gn-900030" not in p          # school: feature code not kept
    assert "bl-gaz-gn-900050" not in p          # no Arabic name anywhere
    assert "bl-gaz-gn-900040" in p              # Arabic name only from the linked Wikidata item
    assert p["bl-gaz-gn-900040"]["name_ar_rule"] == "wikidata_label"
    assert p["bl-gaz-gn-900040"]["wikidata_qid"] == "Q900040"


def test_jeddah_record(built):
    p = _places(built)["bl-gaz-gn-105343"]
    assert p["source"] == "geonames+wikidata"
    assert p["wikidata_qid"] == "Q374365"
    assert p["wikidata_links"][0]["method"] == "p1566+wkdt"
    assert p["name_ar"] == "جدة" and p["name_ar_rule"] == "wikidata_label"
    assert p["name_en"] == "Jeddah"
    assert {"type": "iata", "value": "JED"} in p["codes"]
    assert p["wikipedia_links"] == ["https://en.wikipedia.org/wiki/Jeddah"]
    assert p["coordinates_source"] == "geonames" and p["latitude"] == 21.49012
    assert [n["level"] for n in p["admin_path"]] == [0, 1, 2]
    assert p["admin_path"][1]["geoname_id"] == 104514
    assert p["admin_path"][2]["status"] == "unresolved" and p["admin_path"][2]["geoname_id"] is None
    names = _names(built, "bl-gaz-gn-105343")
    jidda = [n for n in names if n["name"] == "Jiddah" and n["lang"] == "ar"]
    assert jidda and jidda[0]["name_issue"] == "not_arabic_script" and not jidda[0]["is_arabic"]
    hist = [n for n in names if n["name"] == "جدة القديمة"][0]
    assert hist["historic"] and hist["valid_from"] == "1900" and hist["valid_to"] == "1950"
    # جدة and جدّة share a cluster; جده is a separate cluster in the same record
    cl = {n["name"]: n["cluster_id"] for n in names if n["is_arabic"]}
    assert cl["جدة"] == cl["جدّة"] != cl["جده"]
    assert sum(n["is_canonical_ar"] for n in names) == 1
    assert not any(n["lang"] in ("iata", "link", "wkdt") for n in names)


def test_same_name_places_stay_apart(built):
    p = _places(built)
    fam = {p[r]["name_family_id"] for r in ("bl-gaz-gn-900011", "bl-gaz-gn-900012")}
    assert len(fam) == 1
    assert p["bl-gaz-gn-900011"]["record_id"] != p["bl-gaz-gn-900012"]["record_id"]


def test_parent_place_and_hierarchy(built):
    p = _places(built)
    assert p["bl-gaz-gn-900010"]["parent_place_ids"] == ["bl-gaz-gn-105343"]
    assert p["bl-gaz-gn-900010"]["admin_path"][2]["geoname_id"] == 900001
    # Jeddah's Wikidata item is located in the governorate, which GeoNames does not give: no
    # level is comparable beyond admin1, where both agree
    assert p["bl-gaz-gn-105343"]["hierarchy_check"] == "agree"


def test_wikidata_only(built):
    p = _places(built)
    assert "bl-gaz-wd-Q900060" in p                    # village with an Arabic label
    assert "bl-gaz-wd-Q900070" not in p                # mosque: building class
    assert "bl-gaz-wd-Q900080" not in p                # no Arabic label
    assert "bl-gaz-wd-Q374365" not in p                # linked to GeoNames
    w = p["bl-gaz-wd-Q900060"]
    assert w["source"] == "wikidata" and w["feature_class"] == "P"
    assert w["admin_path_source"] == "wikidata_p131_to_geonames"
    assert w["admin_path"][2]["geoname_id"] == 900001
    # same Arabic key within 2 km of a GeoNames record
    assert p["bl-gaz-wd-Q900090"]["possible_duplicate_of"] == "bl-gaz-gn-900012"


def test_admin_units(built):
    units = {u["geoname_id"]: u for u in built["admin_units"]}
    assert units[102358]["level"] == 0
    assert units[104514]["level"] == 1 and units[104514]["parent_geoname_id"] == 102358
    assert units[900001]["level"] == 2 and units[900001]["parent_geoname_id"] == 104514
    assert units[900001]["name_ar"] == "محافظة جدة"


def test_coverage(built):
    sa = [r for r in built["coverage"] if r["country_code"] == "SA"][0]
    assert sa["geonames_features_in_scope"] == 11
    assert sa["with_arabic_name_any"] == sa["with_arabic_name_geonames"] + 1


def test_format_controls_kept_out_of_canonical_names(built):
    from arabic_gazetteer.textnorm import has_format_controls

    p = _places(built)
    w = p["bl-gaz-gn-900020"]
    assert w["name_ar"] == "وادي المثال"            # source name wrapped in U+202B ... U+202C
    assert w["name_en"] == "Wadi Example"            # source name with U+200B inside a word
    assert "وادي المثال" in w["names_ar"] and "Wadi Example" in w["names_latin"]
    names = {n["name"]: n for n in _names(built, "bl-gaz-gn-900020")}
    assert names["\u202bوادي المثال\u202c"]["name_issue"] == "format_control"
    assert names["\u202bوادي المثال\u202c"]["is_canonical_ar"]
    assert names["\u202bوادي المثال\u202c"]["name_norm"] == "وادي المثال"
    assert names["Wadi Ex\u200bample"]["name_issue"] == "format_control"
    assert names["Wadi Ex\u200bample"]["name_norm"] == "wadi example"
    assert names["گرمسير\u200e"]["name_issue"] == "extended_letters,format_control"
    # a name that differs from another only by a format control is one name of the record and
    # in the same cluster
    n = p["bl-gaz-gn-900011"]
    assert n["names_ar"] == ["النزهة"] and n["n_names_ar"] == 1
    rows = _names(built, "bl-gaz-gn-900011")
    assert len({r["cluster_id"] for r in rows if r["is_arabic"]}) == 1
    assert [r["name_issue"] for r in rows if r["name"] == "النزهة\u200f"] == ["format_control"]
    for q in built["places"]:
        assert not has_format_controls(q["name_ar"]) and not has_format_controls(q["name_en"])
        assert not any(has_format_controls(x) for x in q["names_ar"] + q["names_latin"])
    for r in built["names"]:
        assert has_format_controls(r["name"]) == ("format_control" in (r["name_issue"] or ""))


def test_haversine():
    assert abs(haversine_km(21.49, 39.19, 21.54, 39.17) - 5.9) < 0.3

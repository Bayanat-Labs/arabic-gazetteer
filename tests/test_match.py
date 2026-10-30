from arabic_gazetteer import match


def test_orthographic_variants():
    v = dict(match._ortho_variants("مكة المكرمة"))
    assert v["taa_marbuta_to_heh"] == "مكه المكرمه"
    assert "drop_article" not in v      # the first word has no article
    v = dict(match._ortho_variants("أبو ظبي"))
    assert v["hamza_alef_to_alef"] == "ابو ظبي"
    assert v["join_compound"] == "أبوظبي"
    assert dict(match._ortho_variants("الطائف"))["drop_article"] == "طائف"


def test_typo_is_one_edit():
    t = match._typo("الرياض", 7)
    assert t and t != "الرياض" and abs(len(t) - len("الرياض")) <= 1
    assert match._typo("جدة", 1) is None


def test_generate_and_split(built):
    ex = match.generate(built["places"], built["names"])
    assert ex
    ids = {p["record_id"] for p in built["places"]}
    split_of = {}
    for e in ex:
        assert e["target_record_id"] in ids
        assert e["target_record_id"] not in e["distractor_ids"]
        assert split_of.setdefault(e["target_record_id"], e["split"]) == e["split"]
        assert e["label_origin"] in ("source_annotation", "synthetic_rule")
    assert ex == match.generate(built["places"], built["names"])   # deterministic


def test_split_follows_admin1(built):
    by = {}
    for p in built["places"]:
        if len(p["admin_path"]) > 1 and p["admin_path"][1]["status"] == "resolved":
            by.setdefault(p["admin_path"][1]["code"], set()).add(match.split_of(p))
    assert all(len(v) == 1 for v in by.values())


def test_matcher(built):
    m = match.Matcher(built["places"], built["names"])
    assert m.predict("جده") == "bl-gaz-gn-105343"
    assert m.predict("Jidda") == "bl-gaz-gn-105343"
    assert m.predict("JEDDAH") == "bl-gaz-gn-105343"
    # same-name places: admin context decides
    assert m.predict("حي النزهة، جدة") == "bl-gaz-gn-900010"
    assert m.predict("النزهة، منطقة الرياض") == "bl-gaz-gn-900011"
    assert m.predict("لا يوجد") is None
    exact = match.Matcher(built["places"], built["names"], whole_string=True)
    assert exact.predict("جدة") == "bl-gaz-gn-105343"
    assert exact.predict("جده،  جدة") is None


def test_evaluate(built):
    ex = match.generate(built["places"], built["names"])
    res = match.evaluate(ex, built["places"], built["names"])
    assert set(res) == {"exact_string", "normalised_with_admin_context"}
    assert res["normalised_with_admin_context"]["all"]["all"]["n"] == len(ex)

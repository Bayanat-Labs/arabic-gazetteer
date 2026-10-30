from arabic_gazetteer.textnorm import (FORMAT_CONTROLS, ar_core_key, ar_match_key, ar_norm,
                                       has_format_controls, latin_fold, latin_match_key, name_issue,
                                       name_issues, script_issue, script_of, strip_format_controls,
                                       visible)


def test_script_of():
    assert script_of("جدة") == "Arab"
    assert script_of("Jiddah") == "Latn"
    assert script_of("Ra’s al Khaymah") == "Latn"
    assert script_of("جدة Jeddah") == "mixed"
    assert script_of("123") == "other"


def test_cluster_key_is_bayanat_norm_v1():
    assert ar_norm("جِدَّة") == ar_norm("جدة") == "جدة"
    assert ar_norm("أبو ظبي") == "ابو ظبي"
    assert ar_norm("  الرياض   الجديدة ") == "الرياض الجديدة"
    # the cluster key keeps taa marbuta apart from heh
    assert ar_norm("جده") != ar_norm("جدة")


def test_match_key_folds_more():
    assert ar_match_key("جدة") == ar_match_key("جده") == "جده"
    assert ar_match_key("الطائف") == ar_match_key("الطايف") == "طايف"
    assert ar_match_key("حي النزهة، جدة") == "حي نزهه جده"
    assert ar_core_key(ar_match_key("حي النزهة")) == "نزهه"
    assert ar_core_key(ar_match_key("النزهة")) == "نزهه"


def test_latin_keys():
    assert latin_fold("Aṭ Ṭā’if") == "at taif"
    assert latin_match_key("Aṭ Ṭā’if") == latin_match_key("Al-Taif") == "taif"
    assert latin_match_key("Jiddah") == latin_match_key("Jidda") == "jida"
    assert latin_fold("Ra’s al Khaymah") == "ras al khaymah"


def test_name_issue():
    assert name_issue("Jiddah", "Latn", "ar") == "not_arabic_script"
    assert name_issue("گرمسير", "Arab", "ar") == "extended_letters"
    assert name_issue("جدة", "Arab", "latin") == "arabic_script_in_latin_slot"
    assert name_issue("جدة", "Arab", "ar") is None


def test_format_controls():
    cps = ([chr(c) for c in range(0x200B, 0x2010)] + [chr(c) for c in range(0x202A, 0x202F)]
           + [chr(c) for c in range(0x2066, 0x206A)] + ["\u061c", "\ufeff"])
    assert set(cps) == set(FORMAT_CONTROLS) and len(FORMAT_CONTROLS) == 16
    for ch in cps:
        s = "جل" + ch + "يل" + ch
        assert has_format_controls(s)
        assert strip_format_controls(s) == visible(s) == "جليل"
        assert ar_norm(s) == ar_norm("جليل")
        assert latin_fold("Ja" + ch + "lil") == "jalil"
    assert visible(" \u200eجليل \u200f ") == "جليل"
    assert not has_format_controls("جليل") and not has_format_controls(None)
    # other characters are kept: Arabic tatweel and shadda, the no-break space, the soft hyphen
    assert strip_format_controls("جـدّة\u00a0x\u00ad") == "جـدّة\u00a0x\u00ad"


def test_name_issue_format_control():
    assert name_issue("جليل\u200e", "Arab", "ar") == "format_control"
    assert name_issue("\u202bگرمسير\u202c", "Arab", "ar") == "extended_letters,format_control"
    assert name_issue("Jalil\ufeff", "Latn", "latin") == "format_control"
    assert name_issue("Jiddah\u200f", "Latn", "ar") == "not_arabic_script,format_control"
    assert name_issues("extended_letters,format_control") == ["extended_letters", "format_control"]
    assert script_issue("format_control") is None
    assert script_issue("extended_letters,format_control") == "extended_letters"
    assert script_issue(None) is None

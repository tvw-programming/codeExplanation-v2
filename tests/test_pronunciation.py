from src.narrate.pronunciation import split_identifier, spoken_form, build_pronunciation_table


def test_split_identifier_camel_case():
    assert split_identifier("getUserProfile") == ["get", "User", "Profile"]


def test_split_identifier_pascal_case():
    assert split_identifier("AlumniAdminGrid") == ["Alumni", "Admin", "Grid"]


def test_split_identifier_snake_case():
    assert split_identifier("alumni_repository") == ["alumni", "repository"]


def test_split_identifier_route_segment_drops_braces_and_slashes():
    assert split_identifier("/api/v1/alumni/${id}") == ["api", "v1", "alumni", "id"]


def test_split_identifier_consecutive_caps_acronym_then_word():
    assert split_identifier("HTTPServer") == ["HTTP", "Server"]


def test_split_identifier_empty_string():
    assert split_identifier("") == []


def test_spoken_form_expands_known_acronym():
    assert spoken_form("fetchUserID") == "fetch User I D"


def test_spoken_form_json_uses_pronounceable_exception():
    assert spoken_form("parseJSONBody") == "parse Jason Body"


def test_spoken_form_plain_snake_case():
    assert spoken_form("alumni_repository") == "alumni repository"


def test_build_pronunciation_table_deduplicates_and_skips_empty():
    table = build_pronunciation_table(["getUserID", "getUserID", "", "AlumniAdminGrid"])
    assert table == {
        "getUserID": "get User I D",
        "AlumniAdminGrid": "Alumni Admin Grid",
    }

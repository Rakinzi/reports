from reports.slugify import slugify_client_name


def test_simple_name():
    assert slugify_client_name("Union Hardware") == "union_hardware"


def test_extra_whitespace_and_punctuation():
    assert slugify_client_name("  Union Hardware, Inc.  ") == "union_hardware_inc"


def test_already_lowercase_with_underscores():
    assert slugify_client_name("union_hardware") == "union_hardware"


def test_mixed_symbols_collapse_to_single_underscore():
    assert slugify_client_name("Union---Hardware!!!Zim") == "union_hardware_zim"


def test_empty_string_falls_back_to_default():
    assert slugify_client_name("") == "custom_report"


def test_only_punctuation_falls_back_to_default():
    assert slugify_client_name("!!!") == "custom_report"

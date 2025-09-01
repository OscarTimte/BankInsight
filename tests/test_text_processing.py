from finanseer.text_processing import normalize_description

def test_normalize_description():
    """
    Tests the full normalization pipeline for various inputs.
    """
    # Test case with diacritics, stopwords, and extra spaces
    raw_text = "  Betaling via iDEAL bij Café 't Hoekje voor een Tèst-aankoop "
    expected = "cafe t hoekje voor een test aankoop"
    assert normalize_description(raw_text) == expected

    # Test case with only stopwords
    raw_text_stopwords = "SEPA Overboeking via Rabobank"
    expected_stopwords = ""
    assert normalize_description(raw_text_stopwords) == expected_stopwords

    # Test case with numbers and special characters
    raw_text_numbers = "Transactie 12345, met kenmerk: XYZ-987"
    expected_numbers = "transactie 12345 met xyz 987"
    assert normalize_description(raw_text_numbers) == expected_numbers

    # Test empty and None input
    assert normalize_description("") == ""
    assert normalize_description(None) == ""

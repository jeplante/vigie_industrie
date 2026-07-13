from vigie_pipeline.normalize import calculate_change, direction_for, parse_french_number


def test_french_number_normalization() -> None:
    assert parse_french_number("≈ 1 551,25 G$") == 1551.25
    assert parse_french_number("−12,5 %") == -12.5
    assert parse_french_number("inconnu") is None


def test_delta_and_direction() -> None:
    assert calculate_change(4.21, 3.85) == (4.21 - 3.85) / 3.85
    assert calculate_change(1, 0) is None
    assert direction_for(2, 1) == "up"
    assert direction_for(1, 2) == "down"
    assert direction_for(1, 1) == "neutral"

from wr.pdf import parse_en_amount, parse_nl_amount


def test_parse_nl_thousands():
    assert parse_nl_amount("204.895") == 204895.0
    assert parse_nl_amount("3.136") == 3136.0
    assert parse_nl_amount("93.957,02") == 93957.02
    assert parse_nl_amount("-98.913") == -98913.0


def test_parse_en():
    assert parse_en_amount("1,000.00") == 8644.91
    assert parse_en_amount("451.55") == 451.55

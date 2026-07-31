from pathlib import Path

import pytest

from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.sources.great_west import GreatWestAdapter
from vigie_pipeline.sources.ia import IaAdapter
from vigie_pipeline.sources.manulife import ManulifeAdapter
from vigie_pipeline.sources.sunlife import SunLifeAdapter


def _result(path: Path) -> FetchResult:
    return FetchResult(
        url="https://example.com/investors/",
        content=path.read_bytes(),
        content_type="text/html",
        etag='"abc"',
        last_modified="Fri, 11 Jul 2026 10:00:00 GMT",
    )


def test_discovers_new_pdf_and_ignores_unrelated_link(repository_root: Path) -> None:
    documents = discover_documents(
        "test", _result(repository_root / "pipeline/tests/fixtures/source-index.html")
    )
    assert [str(item.canonical_url) for item in documents] == [
        "https://example.com/docs/results-2026-03-31.pdf"
    ]
    assert documents[0].published_at is None


def test_discovery_survives_modified_html(repository_root: Path) -> None:
    documents = discover_documents(
        "test", _result(repository_root / "pipeline/tests/fixtures/source-index-modified.html")
    )
    assert len(documents) == 1
    assert documents[0].title == "Résultats annuels 2025"


def test_company_adapter_extracts_deterministic_metrics(repository_root: Path) -> None:
    html = (repository_root / "pipeline/tests/fixtures/metrics.html").read_text(encoding="utf-8")
    candidates = ManulifeAdapter().extract_metrics(html)
    assert {item.metric_id for item in candidates} == {
        "core_eps",
        "core_earnings",
        "core_roe",
        "licat_ratio",
    }


def test_ia_adapter_prefers_values_over_deltas_and_normalizes_millions() -> None:
    content = """
    Net income attributed to common shareholders (in millions) $137 $186.
    Core EPS of $3.25 (+12% YoY).
    Core earnings (in millions) 298 273 9%.
    Trailing-12-month core ROE of 17.5%.
    The solvency ratio was 134% as at March 31, 2026.
    Total assets under management and assets under administration up 31%
    over the last 12 months to exceed $346 billion.
    """
    candidates = {item.metric_id: item for item in IaAdapter().extract_metrics(content)}
    assert candidates["net_income"].value == 0.137
    assert candidates["core_eps"].value == 3.25
    assert candidates["core_earnings"].value == 0.298
    assert candidates["core_roe"].value == 17.5
    assert candidates["licat_ratio"].value == 134
    assert candidates["assets_under_administration"].value == 346


def test_ia_adapter_recognizes_core_earnings_release_wording() -> None:
    content = """
    Core earnings of $298 million increased 9% year over year.
    """

    candidates = {item.metric_id: item for item in IaAdapter().extract_metrics(content)}

    assert candidates["core_earnings"].value == 0.298


def test_ia_adapter_reads_historical_table_values_and_thousands() -> None:
    content = """
    Net income attributed to common shareholders (in millions) $233 $270.
    Core earnings† 1,074 980 10%.
    Core EPS† of $2.44.
    Core ROE† (trailing 12 months) 14.6%.
    Solvency ratio† 142%.
    Assets under management and administration† (in billions) $229.3 $218.9.
    """

    candidates = {item.metric_id: item for item in IaAdapter().extract_metrics(content)}

    assert candidates["net_income"].value == 0.233
    assert candidates["core_earnings"].value == 1.074
    assert candidates["core_eps"].value == 2.44
    assert candidates["core_roe"].value == 14.6
    assert candidates["licat_ratio"].value == 142
    assert candidates["assets_under_administration"].value == 229.3


def test_ia_adapter_reads_annual_eps_without_currency_symbol() -> None:
    candidates = {
        item.metric_id: item
        for item in IaAdapter().extract_metrics(
            "Core earnings† 956 955. "
            "Core EPS (diluted) (in dollars)† 9.31 8.93. "
            "Core ROE† 14.4%. Solvency ratio† of 145%."
        )
    }

    assert candidates["core_eps"].value == 9.31
    assert candidates["core_earnings"].value == pytest.approx(0.956)
    assert candidates["core_roe"].value == 14.4
    assert candidates["licat_ratio"].value == 145


def test_ia_adapter_ignores_malformed_numeric_matches() -> None:
    candidates = IaAdapter().extract_metrics(
        "Core EPS† of $. Core earnings† (in millions) $. "
        "Assets under management and administration† (in billions) $."
    )

    assert candidates == []


def test_ia_adapter_skips_table_of_contents_before_consolidated_core_earnings() -> None:
    candidates = {
        item.metric_id: item
        for item in IaAdapter().extract_metrics(
            "Profitability 25 Analysis 27 Core Earnings† 28 "
            "Reported Earnings and Core Earnings† Core earnings† 945 $8.85."
        )
    }

    assert candidates["core_earnings"].value == pytest.approx(0.945)


def test_great_west_adapter_normalizes_report_units() -> None:
    content = """
    Base EPS was $1.37 compared with $1.11.
    Base earnings were $1,239 million, up 20%.
    Net earnings of $1,192 million.
    Consolidated base ROE 19.1%.
    The LICAT ratio was 135%.
    Total client assets reached $3.4 trillion.
    """
    candidates = {item.metric_id: item for item in GreatWestAdapter().extract_metrics(content)}
    assert candidates["core_eps"].value == 1.37
    assert candidates["core_earnings"].value == 1.239
    assert candidates["net_income"].value == 1.192
    assert candidates["core_roe"].value == 19.1
    assert candidates["licat_ratio"].value == 135
    assert candidates["total_client_assets"].value == 3.4


def test_great_west_adapter_supports_historical_report_wording() -> None:
    content = """
    Net earnings of $770 million and base earnings1 of $809 million.
    Base earnings per share (EPS) for the first quarter of 2022 of $0.87.
    Total Lifeco Base Return on Equity 14.7%.
    The LICAT ratio was 119%.
    Consolidated assets of $600 billion and assets under administration5
    of $2.2 trillion.
    """

    candidates = {item.metric_id: item for item in GreatWestAdapter().extract_metrics(content)}

    assert candidates["net_income"].value == 0.77
    assert candidates["core_earnings"].value == 0.809
    assert candidates["core_eps"].value == 0.87
    assert candidates["core_roe"].value == 14.7
    assert candidates["licat_ratio"].value == 119
    assert candidates["total_client_assets"].value == 2.2


def test_great_west_adapter_supports_historical_roe_label() -> None:
    content = """
    Total Lifeco Base Return on Equity 17.3%
    """

    candidates = {item.metric_id: item for item in GreatWestAdapter().extract_metrics(content)}

    assert candidates["core_roe"].value == 17.3


def test_great_west_adapter_supports_roe_label_with_footnotes() -> None:
    content = """
    Base ROE2,3,4 17.2% 16.6% 16.1%
    """

    candidates = {item.metric_id: item for item in GreatWestAdapter().extract_metrics(content)}

    assert candidates["core_roe"].value == 17.2


def test_manulife_adapter_prefers_current_values_over_growth_rates() -> None:
    content = """
    Key highlights include Core earnings of $1.8 billion, up 8%.
    Net income attributed to shareholders of $1.1 billion.
    Core EPS of $1.06, up 11%. LICAT ratio of 136%.
    Core ROE of 16.5%.
    Quarterly Results 1Q26 1Q25 Change
    Net income attributed to shareholders $ 1,147 $ 485 149%
    Core earnings $ 1,836 $ 1,767 8%
    Core EPS ($) $ 1.06 $ 0.99 11%
    """
    candidates = {item.metric_id: item for item in ManulifeAdapter().extract_metrics(content)}
    assert candidates["core_eps"].value == 1.06
    assert candidates["core_earnings"].value == 1.836
    assert candidates["net_income"].value == 1.147
    assert candidates["core_roe"].value == 16.5
    assert candidates["licat_ratio"].value == 136


def test_sun_life_adapter_normalizes_release_highlights() -> None:
    content = """
    Underlying net income (2) of $1,050 million increased $5 million.
    Reported net income (3) of $465 million decreased $463 million.
    Underlying EPS (2)(4) of $1.89 increased 4%.
    Underlying return on equity ("ROE") (2) was 18.6%.
    Assets under management ("AUM") (2) of $1,575 billion.
    SLF Inc. LICAT ratio of 143%.
    """
    candidates = {item.metric_id: item for item in SunLifeAdapter().extract_metrics(content)}
    assert candidates["core_eps"].value == 1.89
    assert candidates["core_earnings"].value == 1.05
    assert candidates["net_income"].value == 0.465
    assert candidates["core_roe"].value == 18.6
    assert candidates["licat_ratio"].value == 143
    assert candidates["assets_under_management"].value == 1575


def test_sun_life_adapter_supports_historical_table_wording() -> None:
    content = """
    Q1'22 reported net income of $858 million.
    Underlying net income ($ millions) (1) 843 850.
    Underlying EPS ($) (1)(2) 1.44 1.45.
    Underlying ROE (1) 14.0%.
    Assets under management ("AUM") ($ billions) (1)(3) 1,352 1,304.
    SLF Inc. LICAT ratio of 143%.
    """

    candidates = {item.metric_id: item for item in SunLifeAdapter().extract_metrics(content)}

    assert candidates["net_income"].value == 0.858
    assert candidates["core_earnings"].value == 0.843
    assert candidates["core_eps"].value == 1.44
    assert candidates["core_roe"].value == 14
    assert candidates["licat_ratio"].value == 143
    assert candidates["assets_under_management"].value == 1352


def test_sun_life_adapter_prefers_full_year_roe_in_annual_release() -> None:
    content = """
    Underlying return on equity ("ROE") was 19.1%
    (full year - 18.2%).
    """

    candidates = {item.metric_id: item for item in SunLifeAdapter().extract_metrics(content)}

    assert candidates["core_roe"].value == 18.2

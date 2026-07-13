from datetime import date

from vigie_pipeline.acquire import LlmMetric, _build_observation
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.models import Period, VigieDataset
from vigie_pipeline.sources.base import MetricCandidate


def test_only_llm_metric_receives_anthropic_trace(
    dataset: VigieDataset, project_config: ProjectConfig
) -> None:
    source = next(item for item in project_config.sources if item.id == "mfc-results")
    period = Period(
        period_id="2026-T1",
        period_key="T1",
        type="quarter",
        year=2026,
        quarter=1,
        end_date=date(2026, 3, 31),
        label="T1 2026",
    )
    document = FetchResult(
        url="https://example.com/mfc-q1-2026",
        content=b"official document",
        content_type="text/html",
        etag=None,
        last_modified=None,
    )
    deterministic = _build_observation(
        dataset=dataset,
        source=source,
        period=period,
        document=document,
        title="MFC Q1 2026",
        candidate=MetricCandidate(
            metric_id="core_eps",
            label="Core EPS",
            raw_value="1,06 $",
            value=1.06,
            context="Core EPS was 1.06 dollars.",
        ),
        metric=project_config.metrics["core_eps"],
        config=project_config,
    )
    llm = _build_observation(
        dataset=dataset,
        source=source,
        period=period,
        document=document,
        title="MFC Q1 2026",
        candidate=LlmMetric(
            metric_id="net_income",
            value=1.147,
            display_value="1,147 G$",
            unit="CAD_BILLION",
            context="Net income attributed to shareholders was 1.147 billion.",
            confidence=0.93,
        ),
        metric=project_config.metrics["net_income"],
        config=project_config,
    )
    assert deterministic.quality.extraction_method == "deterministic"
    assert deterministic.quality.llm_trace is None
    assert llm.quality.extraction_method == "anthropic"
    assert llm.quality.llm_trace is not None
    assert llm.quality.llm_trace.task_id.endswith("net_income")

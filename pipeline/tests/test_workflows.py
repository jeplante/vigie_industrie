from pathlib import Path


def test_deploy_workflow_never_refreshes_or_uses_anthropic(repository_root: Path) -> None:
    workflow = (repository_root / ".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")
    assert "vigie_pipeline refresh" not in workflow
    assert "ANTHROPIC_API_KEY" not in workflow
    assert "vigie_pipeline sync-frontend" in workflow
    assert "actions/deploy-pages" in workflow


def test_refresh_workflow_deploys_only_after_success(repository_root: Path) -> None:
    workflow = (repository_root / ".github/workflows/refresh-data.yml").read_text(encoding="utf-8")
    assert "vigie_pipeline refresh" in workflow
    assert "vigie_pipeline validate" in workflow
    assert "vigie_pipeline refresh --dry-run" in workflow
    assert "inputs.dry_run == false" in workflow
    assert "if: needs.refresh.outputs.commit_sha != ''" in workflow
    assert "actions/upload-artifact" in workflow
    assert "needs: refresh" in workflow
    assert "uses: ./.github/workflows/deploy-pages.yml" in workflow
    assert "git add data/published app/public/data" in workflow

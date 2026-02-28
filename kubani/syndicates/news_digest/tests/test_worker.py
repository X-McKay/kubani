"""Tests for the news_digest worker configuration.

Verifies that the worker registers all required activities and workflows
for the three-stage pipeline.
"""


class TestWorkerActivityRegistration:
    """Test that the worker registers all required activities."""

    def test_all_ingest_activities_registered(self):
        """Worker must register all activities used by ingest workflows."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        required = [
            "collect_feeds_activity",
            "run_agent_activity",
            "batch_check_duplicates_activity",
            "store_raw_documents_activity",
        ]
        for name in required:
            assert name in activity_names, f"Missing ingest activity: {name}"

    def test_all_analyze_activities_registered(self):
        """Worker must register all activities used by analyze workflow."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        required = [
            "analyze_document_activity",
            "store_analyzed_document_activity",
        ]
        for name in required:
            assert name in activity_names, f"Missing analyze activity: {name}"

    def test_all_digest_activities_registered(self):
        """Worker must register all activities used by digest workflow."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        required = [
            "query_analyzed_documents_activity",
            "run_agent_activity",
            "send_breaking_news_activity",
            "publish_ui_activity",
        ]
        for name in required:
            assert name in activity_names, f"Missing digest activity: {name}"

    def test_no_duplicate_activities(self):
        """Worker should not register duplicate activities."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        assert len(activity_names) == len(set(activity_names)), (
            f"Duplicate activities found: "
            f"{[n for n in activity_names if activity_names.count(n) > 1]}"
        )


class TestWorkerWorkflowRegistration:
    """Test that the worker registers all required workflows."""

    def test_all_workflows_registered(self):
        """Worker must register all pipeline workflows."""
        from news_digest_syndicate.worker import get_workflows

        workflows = get_workflows()
        workflow_names = [w.__name__ for w in workflows]

        required = [
            "RSSIngestWorkflow",
            "ArxivIngestWorkflow",
            "GitHubIngestWorkflow",
            "AnalyzeDocumentWorkflow",
            "NewsDigestWorkflow",
        ]
        for name in required:
            assert name in workflow_names, f"Missing workflow: {name}"

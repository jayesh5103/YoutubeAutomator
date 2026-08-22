import unittest
import database
from pipeline_state import PipelineStatus, transition
import youtube_uploader
import logger_utils

class TestWorkflowGates(unittest.TestCase):
    def setUp(self):
        database.init_db()

    def test_pipeline_creation_and_transitions(self):
        # 1. Create pipeline
        pid = database.create_pipeline_entry("Test Binary Search", "coding.yaml")
        p = database.get_pipeline(pid)
        self.assertEqual(p["status"], PipelineStatus.DRAFT.value)

        # 2. Legal state transitions
        transition(pid, PipelineStatus.SCRIPT_GENERATED)
        self.assertEqual(database.get_pipeline(pid)["status"], PipelineStatus.SCRIPT_GENERATED.value)

        transition(pid, PipelineStatus.SCRIPT_REVIEW)
        self.assertEqual(database.get_pipeline(pid)["status"], PipelineStatus.SCRIPT_REVIEW.value)

        transition(pid, PipelineStatus.RENDERING)
        self.assertEqual(database.get_pipeline(pid)["status"], PipelineStatus.RENDERING.value)

        transition(pid, PipelineStatus.RENDERED)
        self.assertEqual(database.get_pipeline(pid)["status"], PipelineStatus.RENDERED.value)

        transition(pid, PipelineStatus.PENDING_REVIEW)
        self.assertEqual(database.get_pipeline(pid)["status"], PipelineStatus.PENDING_REVIEW.value)

    def test_illegal_state_transition(self):
        pid = database.create_pipeline_entry("Test Illegal State", "coding.yaml")
        # Direct DRAFT -> APPROVED should raise ValueError
        with self.assertRaises(ValueError):
            transition(pid, PipelineStatus.APPROVED)

    def test_mandatory_upload_permission_gate(self):
        pid = database.create_pipeline_entry("Test Mandatory Gate", "coding.yaml")
        transition(pid, PipelineStatus.SCRIPT_GENERATED)
        transition(pid, PipelineStatus.SCRIPT_REVIEW)
        transition(pid, PipelineStatus.RENDERING)
        transition(pid, PipelineStatus.RENDERED)
        transition(pid, PipelineStatus.PENDING_REVIEW)

        # Attempting upload on PENDING_REVIEW should raise PermissionError
        with self.assertRaises(PermissionError):
            youtube_uploader.upload_video(
                video_path="temp_test_video.mp4",
                title="Test Title",
                description="Test Desc",
                tags=["test"],
                pipeline_id=pid
            )

    def test_logs_recorded(self):
        pid = database.create_pipeline_entry("Test Logger", "coding.yaml")
        logger_utils.log_event(pid, "TEST_STAGE", "INFO", "Sample test log entry")
        logs = database.get_pipeline_logs(pipeline_id=pid, stage="TEST_STAGE")
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["message"], "Sample test log entry")

if __name__ == "__main__":
    unittest.main()

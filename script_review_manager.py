"""
Script Review Manager for YoutubeAutomator
Manages pre-rendering script inspection, editing history, and approval.
"""

import json
import logging
import database
from pipeline_state import PipelineStatus, transition

logger = logging.getLogger("YoutubeAutomator")

def get_script_for_review(pipeline_id: int) -> dict:
    """
    Returns pipeline details, parsed beats JSON array, and script edit history.
    """
    pipeline = database.get_pipeline(pipeline_id)
    if not pipeline:
        raise ValueError(f"Pipeline {pipeline_id} not found.")

    beats = []
    if pipeline.get("script_json"):
        try:
            beats = json.loads(pipeline["script_json"])
        except Exception as e:
            logger.error(f"Failed to parse script_json for pipeline {pipeline_id}: {e}")

    conn = database.sqlite3.connect(database.DB_PATH)
    conn.row_factory = database.sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM script_edit_history WHERE pipeline_id = ? ORDER BY version DESC",
        (pipeline_id,)
    )
    history_rows = c.fetchall()
    conn.close()

    history = [dict(h) for h in history_rows]

    return {
        "pipeline": pipeline,
        "beats": beats,
        "history": history
    }

def save_script_edit(pipeline_id: int, updated_beats: list, edit_note: str = None) -> int:
    """
    Saves an updated beat array as a new version in script_edit_history and updates video_pipeline.
    Does NOT change pipeline status by itself.
    """
    script_json = json.dumps(updated_beats, ensure_ascii=False, indent=2)
    version = database.save_script_version(pipeline_id, script_json, edited_by='user', edit_note=edit_note)
    database.log_pipeline_event(pipeline_id, "SCRIPT_EDIT", "INFO", f"Saved script version v{version}" + (f": {edit_note}" if edit_note else ""))
    return version

def approve_script(pipeline_id: int) -> dict:
    """
    Transitions pipeline from SCRIPT_REVIEW (or SCRIPT_GENERATED) to RENDERING.
    """
    pipeline = database.get_pipeline(pipeline_id)
    if not pipeline:
        raise ValueError(f"Pipeline {pipeline_id} not found.")

    current_status = PipelineStatus(pipeline["status"])
    if current_status not in [PipelineStatus.SCRIPT_REVIEW, PipelineStatus.SCRIPT_GENERATED, PipelineStatus.REJECTED]:
        logger.warning(f"Approving script for pipeline {pipeline_id} from status {current_status}")

    transition(pipeline_id, PipelineStatus.RENDERING)
    database.log_pipeline_event(pipeline_id, "SCRIPT_APPROVAL", "INFO", "Script approved for rendering.")
    return get_script_for_review(pipeline_id)

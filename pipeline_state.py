"""
Pipeline State Machine for YoutubeAutomator
Enforces explicit state transitions for video creation and upload approval.
"""

import logging
from enum import Enum

logger = logging.getLogger("YoutubeAutomator")

class PipelineStatus(str, Enum):
    DRAFT = "DRAFT"                        # topic chosen, nothing generated yet
    SCRIPT_GENERATED = "SCRIPT_GENERATED"   # LLM produced script + beats
    SCRIPT_REVIEW = "SCRIPT_REVIEW"         # waiting on human in Script Editor panel
    RENDERING = "RENDERING"                 # beat_renderer + TTS + assembly running
    RENDERED = "RENDERED"                   # final mp4 exists, health check passed
    PENDING_REVIEW = "PENDING_REVIEW"       # waiting on human in Review & Approve tab
    NEEDS_REGENERATION = "NEEDS_REGENERATION"  # specific beat(s) flagged, looping back
    APPROVED = "APPROVED"                   # human approved, upload may proceed
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    REJECTED = "REJECTED"                   # human rejected, needs rework or discard
    FAILED = "FAILED"                       # unrecoverable pipeline error

# Legal state transitions — strictly enforced
TRANSITIONS = {
    PipelineStatus.DRAFT: {PipelineStatus.SCRIPT_GENERATED, PipelineStatus.FAILED},
    PipelineStatus.SCRIPT_GENERATED: {PipelineStatus.SCRIPT_REVIEW, PipelineStatus.FAILED, PipelineStatus.RENDERING},
    PipelineStatus.SCRIPT_REVIEW: {PipelineStatus.RENDERING, PipelineStatus.REJECTED, PipelineStatus.FAILED},
    PipelineStatus.RENDERING: {PipelineStatus.RENDERED, PipelineStatus.FAILED, PipelineStatus.NEEDS_REGENERATION},
    PipelineStatus.RENDERED: {PipelineStatus.PENDING_REVIEW, PipelineStatus.FAILED},
    PipelineStatus.PENDING_REVIEW: {
        PipelineStatus.APPROVED,
        PipelineStatus.REJECTED,
        PipelineStatus.NEEDS_REGENERATION,
        PipelineStatus.PENDING_REVIEW,  # save draft, stays in review
        PipelineStatus.SCRIPT_REVIEW,
    },
    PipelineStatus.NEEDS_REGENERATION: {PipelineStatus.RENDERING},
    PipelineStatus.APPROVED: {PipelineStatus.UPLOADING, PipelineStatus.FAILED},
    PipelineStatus.UPLOADING: {PipelineStatus.UPLOADED, PipelineStatus.FAILED},
    PipelineStatus.REJECTED: {PipelineStatus.SCRIPT_REVIEW, PipelineStatus.DRAFT},
}

def transition(pipeline_id: int, new_status: PipelineStatus, note: str | None = None) -> PipelineStatus:
    """
    Validate and apply a status change for a video pipeline entry.
    Updates the database and logs the state change event.
    Raises ValueError on invalid transitions.
    """
    from database import get_pipeline, update_pipeline_status, log_pipeline_event

    current_pipeline = get_pipeline(pipeline_id)
    if not current_pipeline:
        raise ValueError(f"Pipeline with ID {pipeline_id} does not exist.")

    current_status = PipelineStatus(current_pipeline["status"])

    # Allow transitioning to the same status (e.g. updating draft/notes)
    if current_status != new_status:
        allowed_next = TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise ValueError(
                f"Illegal state transition for pipeline {pipeline_id}: "
                f"cannot move from '{current_status.value}' to '{new_status.value}'."
            )

    update_pipeline_status(pipeline_id, new_status.value, rejection_reason=note if new_status == PipelineStatus.REJECTED else None)
    log_msg = f"Status changed from {current_status.value} to {new_status.value}" + (f": {note}" if note else "")
    log_pipeline_event(pipeline_id, "STATE_TRANSITION", "INFO", log_msg)
    logger.info(f"[Pipeline {pipeline_id}] {log_msg}")

    return new_status

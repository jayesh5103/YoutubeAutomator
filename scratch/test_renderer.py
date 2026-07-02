import os
import sys
import logging

# Ensure parent directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from render_worker import _render_single_job
from db_migration import run_migration

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Run DB migration to ensure clean state
    run_migration()
    
    job_data = {
        "topic": "Kadane's Algorithm",
        "niche_file": "coding.yaml",
        "worker_id": 99,
        "channel_name": "Test SDE Channel"
    }
    
    print("\n🚀 Starting dry-run rendering pipeline test...")
    result = _render_single_job(job_data)
    
    print("\n📊 Render Pipeline Result:")
    import pprint
    pprint.pprint({k: v for k, v in result.items() if k != 'storyboard_beats'})
    
    if result.get('success'):
        print(f"\n✅ Video successfully generated at: {result['video_path']}")
        print(f"✅ Storyboard had {result.get('beat_count')} beats, average beat duration: {result.get('avg_beat_duration'):.2f}s")
        print(f"✅ Classed hook style: {result.get('hook_style')}")
    else:
        print("\n❌ Pipeline failed:", result.get('error'))

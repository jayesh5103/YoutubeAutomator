from utils import delete_uploaded_videos
import sys

if __name__ == "__main__":
    # If run with --force, skip confirmation
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        delete_uploaded_videos()
    else:
        confirm = input("Are you sure you want to delete all uploaded videos from 'renders/uploaded'? (y/n): ")
        if confirm.lower() == 'y':
            delete_uploaded_videos()
        else:
            print("Cleanup cancelled.")

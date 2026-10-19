import os
import sys
from huggingface_hub import HfApi

from pathlib import Path

env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.environ.get("HF_TOKEN")

REPO_ID = "m3ik18dp/MashLoop"

api = HfApi()

ALLOW_PATTERNS = [
    "app.py",
    "requirements.txt",
    ".gitignore",
]

if __name__ == "__main__":
    print(f"Uploading clean loader files to Hugging Face Space: {REPO_ID}...")
    try:
        commit_info = api.upload_folder(
            folder_path=".",
            repo_id=REPO_ID,
            repo_type="space",
            token=TOKEN,
            commit_message="feat: update loader files on Hugging Face Spaces",
            allow_patterns=ALLOW_PATTERNS
        )
        print("SUCCESS")
        print(commit_info)
        print("Restarting Space container...")
        res = api.restart_space(REPO_ID, token=TOKEN)
        print(f"Space status: {res.stage}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

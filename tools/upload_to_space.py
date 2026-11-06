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

REPOS = ["m3ik18dp/meikova-loop", "m3ik18dp/MashLoop"]

api = HfApi()

ALLOW_PATTERNS = [
    "app.py",
    "requirements.txt",
    "packages.txt",
    ".gitignore",
]

if __name__ == "__main__":
    for repo_id in REPOS:
        print(f"Uploading clean loader files to Hugging Face Space: {repo_id}...")
        try:
            commit_info = api.upload_folder(
                folder_path=".",
                repo_id=repo_id,
                repo_type="space",
                token=TOKEN,
                commit_message="feat: update loader files on Hugging Face Spaces",
                allow_patterns=ALLOW_PATTERNS
            )
            print(f"SUCCESS: {repo_id}")
            print(commit_info)
            print(f"Triggering Space rebuild: {repo_id}...")
            try:
                res = api.restart_space(repo_id, token=TOKEN)
                print(f"Space status ({repo_id}): {getattr(getattr(res, 'runtime', None), 'stage', 'OK')}")
            except Exception as rex:
                print(f"Space auto-restarts on commit ({rex})")
        except Exception as e:
            print(f"ERROR ({repo_id}): {e}", file=sys.stderr)

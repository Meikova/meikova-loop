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

ignore_patterns = [
    ".git/**",
    ".venv/**",
    "venv/**",
    "data/**",
    "videos/**",
    "build/**",
    "dist/**",
    "node_modules/**",
    "android/**",
    "ios/**",
    ".agents/**",
    "AGENTS.md",
    "docs/agent-handoff.md",
    "*.log",
    "*.pyc",
    "__pycache__/**",
    ".idea/**",
    ".vscode/**",
    "*.lnk",
    ".env*",
    ".qa/**",
    ".scratch/**",
    "tools/**",
    "build-exe.bat",
    "run-desktop.*",
    "installer.iss",
    "capacitor.config.json"
]

if __name__ == "__main__":
    print(f"Uploading clean files to Hugging Face Space: {REPO_ID}...")
    try:
        commit_info = api.upload_folder(
            folder_path=".",
            repo_id=REPO_ID,
            repo_type="space",
            token=TOKEN,
            commit_message="feat: deploy MashLoop web app to Hugging Face Spaces",
            ignore_patterns=ignore_patterns
        )
        print("SUCCESS")
        print(commit_info)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

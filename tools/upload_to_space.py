import os
import sys
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN")
if not TOKEN:
    print("ERROR: HF_TOKEN environment variable is required.", file=sys.stderr)
    sys.exit(1)

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

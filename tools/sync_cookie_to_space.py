import os
import sys
from pathlib import Path
from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loopbox.cookies import parse_cookies_to_dict, serialize_netscape_cookies

env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "m3ik18dp/MashLoop"

json_file = Path(r"E:\Downloads\www.youtube.com_20-10-2026.json")
if not json_file.exists():
    print(f"ERROR: Cookie file not found: {json_file}")
    sys.exit(1)

raw_content = json_file.read_text(encoding="utf-8")
parsed = parse_cookies_to_dict(raw_content)
netscape_str = serialize_netscape_cookies(parsed)

print(f"Parsed {len(parsed)} cookies from {json_file.name}")
print(f"Uploading YOUTUBE_COOKIES secret to Hugging Face Space: {REPO_ID}...")

api = HfApi()
try:
    api.add_space_secret(repo_id=REPO_ID, key="YOUTUBE_COOKIES", value=netscape_str, token=TOKEN)
    print("SUCCESS: Space Secret 'YOUTUBE_COOKIES' added successfully!")
    print("Restarting Space to apply new secret...")
    res = api.restart_space(repo_id=REPO_ID, token=TOKEN)
    print(f"Space status: {res.stage}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

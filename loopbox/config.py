import json
import os
from pathlib import Path
import sys

APP_VERSION = "1.0.26"
ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

def _load_env_file() -> None:
    candidates = [
        ROOT / ".env",
        Path.cwd() / ".env",
        Path(sys.executable).parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_file in candidates:
        if env_file and env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            except Exception:
                pass

_load_env_file()

def _resolve_anchor_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    p = base / "MeikovaLoop"
    p.mkdir(parents=True, exist_ok=True)
    return p

ANCHOR_DIR = _resolve_anchor_dir()
STORAGE_CONFIG_FILE = ANCHOR_DIR / "storage_config.json"


def get_default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return ANCHOR_DIR / "data"
    return ROOT / "data"


def _resolve_data_dir() -> Path:
    if os.environ.get("MEIKOVA_LOOP_DATA"):
        p = Path(os.environ["MEIKOVA_LOOP_DATA"]).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if STORAGE_CONFIG_FILE.exists():
        try:
            cfg = json.loads(STORAGE_CONFIG_FILE.read_text(encoding="utf-8"))
            custom_path = cfg.get("data_dir")
            if custom_path:
                p = Path(custom_path).resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass

    # Auto-discovery fallback: scan fixed partitions for existing MeikovaLoopData
    try:
        import psutil
        for part in psutil.disk_partitions():
            if 'fixed' in part.opts or 'rw' in part.opts:
                cand = Path(part.mountpoint) / "MeikovaLoopData"
                if cand.is_dir() and (cand / "library").is_dir():
                    try:
                        STORAGE_CONFIG_FILE.write_text(
                            json.dumps({"data_dir": str(cand.resolve())}, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                    return cand.resolve()
    except Exception:
        pass

    p = get_default_data_dir().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

DATA_DIR = _resolve_data_dir()
LIBRARY_DIR = DATA_DIR / "library"
# One file per ordered pair of songs: the transitions from the first to the
# second. Shared by every listener, so a pair is only ever computed once.
PAIRS_DIR = DATA_DIR / "pairs"
# Per-song transition lists assembled for the whole local library, read by the
# test tools (tools/sim_player.mjs, link_report.py). Written by `cli relink`.
TRANSITIONS_DIR = DATA_DIR / "transitions"
WEB_DIR = ROOT / "web"
MODELS_DIR = ROOT / "data" / "models"
if not MODELS_DIR.exists() and (DATA_DIR / "models").exists():
    MODELS_DIR = DATA_DIR / "models"


def get_storage_info() -> dict:
    import shutil
    import psutil

    cur_path = str(DATA_DIR)
    def_path = str(get_default_data_dir())
    is_custom = Path(cur_path).resolve() != Path(def_path).resolve()

    free_gb, total_gb = 0.0, 0.0
    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_gb = round(usage.free / (1024 ** 3), 1)
        total_gb = round(usage.total / (1024 ** 3), 1)
    except Exception:
        pass

    used_mb = 0.0
    try:
        size_bytes = sum(f.stat().st_size for f in DATA_DIR.rglob('*') if f.is_file())
        used_mb = round(size_bytes / (1024 ** 2), 1)
    except Exception:
        pass

    drives = []
    try:
        for p in psutil.disk_partitions():
            if 'fixed' in p.opts or 'rw' in p.opts:
                try:
                    u = shutil.disk_usage(p.mountpoint)
                    drives.append({
                        "mount": p.mountpoint,
                        "free_gb": round(u.free / (1024 ** 3), 1),
                        "total_gb": round(u.total / (1024 ** 3), 1),
                    })
                except Exception:
                    pass
    except Exception:
        pass

    return {
        "data_dir": cur_path,
        "default_dir": def_path,
        "is_custom": is_custom,
        "free_gb": free_gb,
        "total_gb": total_gb,
        "used_mb": used_mb,
        "drives": drives,
    }


def apply_data_dir(new_path: Path | str, migrate: bool = False) -> dict:
    global DATA_DIR, LIBRARY_DIR, PAIRS_DIR, TRANSITIONS_DIR, MODELS_DIR
    target = Path(new_path).resolve()
    target.mkdir(parents=True, exist_ok=True)

    test_file = target / ".write_test"
    try:
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as e:
        raise ValueError(f"Không có quyền ghi vào thư mục được chọn: {e}")

    old_dir = DATA_DIR
    if migrate and old_dir.exists() and old_dir.resolve() != target:
        import shutil
        for item in old_dir.iterdir():
            if item.name in (".write_test", "desktop_profile", "tmp"):
                continue
            dest = target / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    shutil.copy2(item, dest)
                    try:
                        item.unlink()
                    except OSError:
                        pass
            except Exception:
                pass

    STORAGE_CONFIG_FILE.write_text(json.dumps({"data_dir": str(target)}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        (target / "storage_marker.json").write_text(
            json.dumps({"app": "Meikova Loop", "type": "library"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if (ANCHOR_DIR / "settings.json").exists() and not (target / "settings.json").exists():
            import shutil
            shutil.copy2(ANCHOR_DIR / "settings.json", target / "settings.json")
    except Exception:
        pass

    DATA_DIR = target
    LIBRARY_DIR = DATA_DIR / "library"
    PAIRS_DIR = DATA_DIR / "pairs"
    TRANSITIONS_DIR = DATA_DIR / "transitions"
    if not (ROOT / "data" / "models").exists() and (DATA_DIR / "models").exists():
        MODELS_DIR = DATA_DIR / "models"

    for d in (LIBRARY_DIR, PAIRS_DIR, TRANSITIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    try:
        import sys
        if "loopbox.library" in sys.modules:
            lib = sys.modules["loopbox.library"]
            lib.LIBRARY_DIR = LIBRARY_DIR
            lib.PAIRS_DIR = PAIRS_DIR
            lib.TRANSITIONS_DIR = TRANSITIONS_DIR
        if "loopbox.server" in sys.modules:
            srv = sys.modules["loopbox.server"]
            srv.DATA_DIR = DATA_DIR
            srv.SETTINGS_FILE = DATA_DIR / "settings.json"
    except Exception:
        pass

    return get_storage_info()


def reset_default_data_dir() -> dict:
    if STORAGE_CONFIG_FILE.exists():
        try:
            STORAGE_CONFIG_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    return apply_data_dir(get_default_data_dir(), migrate=False)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name) or default)


HOST = os.environ.get("MEIKOVA_LOOP_HOST") or "0.0.0.0"
PORT = _env_int("MEIKOVA_LOOP_PORT", 8765)

# Hosted for many listeners (MEIKOVA_LOOP_MULTIUSER=1): every visit starts an empty
# library of its own, and songs anyone has added are kept as a shared cache.
# Off (the default) it is the personal app: one library, kept between visits.
MULTIUSER = os.environ.get("MEIKOVA_LOOP_MULTIUSER") == "1"
# Songs analysed at once (each worker process holds its own models on the GPU)
# and processes computing transitions between songs.
def _detect_analysis_workers() -> int:
    env_val = os.environ.get("MEIKOVA_LOOP_ANALYSIS_WORKERS")
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    # Avoid heavy torch import during module init if not already loaded
    if "torch" in sys.modules:
        try:
            import torch
            if torch.cuda.is_available():
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                if vram_gb >= 15.0:
                    return 3
                elif vram_gb >= 7.5:
                    return 2
                else:
                    return 1
        except Exception:
            pass
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        cores = psutil.cpu_count(logical=False) or os.cpu_count() or 4
        if cores >= 16 and ram_gb >= 24.0:
            return 2
    except Exception:
        pass
    return 1


def _detect_download_workers() -> int:
    env_val = os.environ.get("MEIKOVA_LOOP_DOWNLOAD_WORKERS")
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    cores = os.cpu_count() or 4
    if cores >= 8:
        return 4
    elif cores >= 4:
        return 3
    return 2


ANALYSIS_WORKERS = _detect_analysis_workers()
DOWNLOAD_WORKERS = _detect_download_workers()
LINK_WORKERS = _env_int("MEIKOVA_LOOP_LINK_WORKERS", 1)
def _default_worker_threads() -> int:
    cores = os.cpu_count() or 4
    if cores <= 2:
        return 1
    elif cores <= 4:
        return 2
    else:
        return min(4, cores - 2)

# CPU threads per worker process (numpy, librosa, torch on the CPU parts) - capped to avoid core saturation
WORKER_THREADS = _env_int("MEIKOVA_LOOP_WORKER_THREADS", _default_worker_threads())
# Shared cache size: past it, the songs nobody has used for longest go.
MAX_STORE_GB = float(os.environ.get("MEIKOVA_LOOP_MAX_STORE_GB") or 0)  # 0 = no limit
MAX_SESSION_TRACKS = _env_int("MEIKOVA_LOOP_MAX_SESSION_TRACKS", 60)
MAX_PLAYLIST = _env_int("MEIKOVA_LOOP_MAX_PLAYLIST", 50)
MAX_UPLOAD_MB = _env_int("MEIKOVA_LOOP_MAX_UPLOAD_MB", 500)
SESSION_TTL_S = _env_int("MEIKOVA_LOOP_SESSION_TTL_H", 12) * 3600
# Hosted, the sound of a song nobody has used for this long is deleted; what the
# analysis made stays, so adding the song again only fetches the sound (an
# uploaded file has to be uploaded again). The sample library and the songs an
# open library holds are kept.
AUDIO_TTL_S = _env_int("MEIKOVA_LOOP_AUDIO_TTL_H", 12) * 3600
# JavaScript runtime yt-dlp uses for YouTube's player challenges (node or deno).
JS_RUNTIME = os.environ.get("MEIKOVA_LOOP_JS_RUNTIME") or "node"

# Audio stored for playback and analysis: identical samples on both sides.
SAMPLE_RATE = 44100
ANALYSIS_SR = 22050
TARGET_LUFS = -14.0
# Up to 60 minutes per track on Desktop / local personal app.
# Multi-user / hosted environments (Space) default to 15 minutes to preserve resources.
MAX_DURATION_S = _env_int("MEIKOVA_LOOP_MAX_DURATION_S", 15 * 60 if MULTIUSER else 60 * 60)

DEVICE = "cuda"  # falls back to cpu at runtime when CUDA is unavailable

# Bump when the analysis output changes in a way that requires re-analysis.
ANALYSIS_VERSION = 6
# Bump when only the cross-track transition search changes.
TRANSITIONS_VERSION = 10

for d in (LIBRARY_DIR, PAIRS_DIR, TRANSITIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)

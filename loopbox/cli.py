"""Command line: python -m loopbox.cli add "<url or search>" | analyze <id> | relink | list"""
import argparse
import sys

from . import download, ingest, library


def _print_update(m: dict) -> None:
    print(f"\r  {m['id']}  {m.get('stage', ''):<12} {int(100 * m.get('progress', 0)):3d}%", end="", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="loopbox")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="download + analyse YouTube videos, playlists or searches")
    p.add_argument("items", nargs="+")
    p = sub.add_parser("analyze", help="re-run analysis for tracks already downloaded")
    p.add_argument("ids", nargs="*")
    sub.add_parser("relink", help="recompute every cross-song transition")
    sub.add_parser("rejump", help="recompute in-song jumps from stored features, then relink")
    sub.add_parser("list")
    args = ap.parse_args(argv)

    if args.cmd == "add":
        for text in args.items:
            for entry in download.resolve(text):
                meta = ingest.register(entry)
                print(f"{entry['id']}  {entry['title']}")
                if meta.get("status") != "ready":
                    ingest.process(entry["id"], _print_update)
                    print()
    elif args.cmd == "analyze":
        for tid in args.ids or [m["id"] for m in library.list_tracks()]:
            print(tid)
            ingest.process(tid, _print_update)
            print()
    elif args.cmd == "rejump":
        from .analysis import pipeline, transitions
        for m in library.list_tracks():
            tid = m["id"]
            if not library.features_path(tid).exists() or not library.analysis_path(tid).exists():
                continue
            jr = pipeline.recompute_jumps(tid)
            library.update(tid, status="ready", stage="ready", progress=1.0, error=None)
            print(f"{tid}  jumps={len(jr['jumps'])}  bridges={jr['bridges']}  lbp={jr['lbp']}")
        transitions.relink_all()
    elif args.cmd == "relink":
        from .analysis import transitions
        transitions.relink_all(lambda i, n: print(f"\r  {i}/{n}", end="", flush=True))
        print()
    elif args.cmd == "list":
        for m in library.list_tracks():
            print(f"{m['id']}  {m.get('status', '?'):<10} {m.get('bpm', ''):>6} {m.get('camelot', ''):>4} "
                  f"jumps={m.get('jumps', '')} {m.get('title', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

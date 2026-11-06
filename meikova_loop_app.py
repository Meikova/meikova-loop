"""Meikova Loop Desktop Application Launcher."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    splash = None
    if "--multiprocessing-fork" not in sys.argv:
        try:
            from loopbox.splash import start_splash
            splash = start_splash()
        except Exception:
            pass

    from loopbox.desktop import main
    main(splash=splash)

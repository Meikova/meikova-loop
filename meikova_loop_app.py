"""Meikova Loop Desktop Application Launcher."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from loopbox.desktop import main
    main()

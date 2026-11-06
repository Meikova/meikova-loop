"""Meikova Loop Desktop Application Launcher."""
import multiprocessing
import os
import sys

if sys.platform == "win32":
    cur_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    flags = [
        "--use-fake-ui-for-media-stream",
        "--enable-features=AudioServiceOutOfProcess",
        "--autoplay-policy=no-user-gesture-required",
    ]
    for flag in flags:
        if flag not in cur_args:
            cur_args = (cur_args + " " + flag).strip()
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = cur_args
    try:
        import webview.platforms.edgechromium as ec
        _orig_ec_init = ec.EdgeChrome.__init__
        def _patched_ec_init(self, form, window, cache_dir):
            _orig_ec_init(self, form, window, cache_dir)
            try:
                props = self.webview.CreationProperties
                cur = (props.AdditionalBrowserArguments or "").strip()
                for f in flags:
                    if f not in cur:
                        cur += " " + f
                props.AdditionalBrowserArguments = cur.strip()
            except Exception:
                pass
        ec.EdgeChrome.__init__ = _patched_ec_init
    except Exception:
        pass

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

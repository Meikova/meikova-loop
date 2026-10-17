"""Mash ∞ Loop (package name: loopbox): an Infinite-Jukebox style player that analyses YouTube audio locally
and chains the songs of a local library into one endless stream."""
import sys

# Silence known Windows asyncio bug where closing client connections abruptly (e.g. aborting audio range streams)
# causes ProactorEventLoop._call_connection_lost to raise ConnectionResetError: [WinError 10054].
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _silenced_call_connection_lost(self, exc):
            try:
                _orig_call_connection_lost(self, exc)
            except (ConnectionResetError, OSError):
                if getattr(self, "_sock", None) is not None:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                if getattr(self, "_server", None) is not None:
                    try:
                        self._server._detach()
                    except Exception:
                        pass
                    self._server = None
                self._called_connection_lost = True

        _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
    except Exception:
        pass

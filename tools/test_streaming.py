"""Test chunked streaming and HTTP 206 Range requests for loopbox server."""
import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loopbox import server, sessions


def test_chunked_streaming_and_range():
    # Setup dummy session and dummy audio file
    v = sessions.create()
    key = v.key
    assert key is not None

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        # Create 200 KB dummy audio data
        file_size = 200 * 1024
        raw_data = bytes((i % 256) for i in range(file_size))
        tmp.write(raw_data)
        tmp_path = Path(tmp.name)

    try:
        kid = "dummy_track"
        ks = np.frombuffer(server.keystream(key, kid), dtype=np.uint8)
        expected_full_scrambled = (np.frombuffer(raw_data, dtype=np.uint8) ^ np.resize(ks, file_size)).tobytes()

        # 1. Full Stream (no Range header)
        class DummyRequest:
            headers = {}
            client = None

        resp_full = server._send_sound(tmp_path, kid, DummyRequest(), v)
        assert resp_full.status_code == 200
        assert resp_full.headers.get("Accept-Ranges") == "bytes"
        assert resp_full.headers.get("Content-Length") == str(file_size)

        import asyncio

        async def collect(resp):
            chunks = []
            async for chunk in resp.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        streamed_full = asyncio.run(collect(resp_full))
        assert streamed_full == expected_full_scrambled, "Full stream does not match expected keystream output!"

        # 2. Range Request (bytes=1000-49999)
        class DummyRangeRequest:
            headers = {"range": "bytes=1000-49999"}
            client = None

        resp_range = server._send_sound(tmp_path, kid, DummyRangeRequest(), v)
        assert resp_range.status_code == 206
        assert resp_range.headers.get("Content-Range") == f"bytes 1000-49999/{file_size}"
        assert resp_range.headers.get("Content-Length") == str(49999 - 1000 + 1)

        streamed_range = asyncio.run(collect(resp_range))
        assert streamed_range == expected_full_scrambled[1000:50000], "Range stream does not match expected slice!"

        print("PASS: Chunked Streaming and HTTP 206 Range tests succeeded with exact parity!")

    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sessions.MULTIUSER = True
    server.MULTIUSER = True
    test_chunked_streaming_and_range()

#!/usr/bin/env python3
"""Run the monitor with curl for RSC feeds that reject Python's TLS client."""
import io
import runpy
import subprocess
import urllib.error
import urllib.request

_original_urlopen = urllib.request.urlopen

def urlopen_with_rsc_fallback(request, *args, **kwargs):
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    if "feeds.rsc.org" in url:
        try:
            response = subprocess.run(
                ["curl", "--fail", "--location", "--http1.1", "--silent", "--show-error",
                 "--max-time", "30", "-A", "ChembioLabMonitor/1.0", url],
                check=True, capture_output=True,
            )
            return io.BytesIO(response.stdout)
        except subprocess.CalledProcessError as exc:
            raise urllib.error.URLError(exc.stderr.decode("utf-8", "replace").strip()) from exc
    return _original_urlopen(request, *args, **kwargs)

urllib.request.urlopen = urlopen_with_rsc_fallback
runpy.run_path("work/run_today_monitor.py", run_name="__main__")

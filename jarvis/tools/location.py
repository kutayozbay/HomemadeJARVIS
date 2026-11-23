"""Where you are right now, asked from the Windows location service when a tool needs it.

Nothing is stored: the answer is kept in memory for 30 minutes (so a second question is instant)
and is gone when FRIDAY stops. The coordinates are never written to disk or to the log.
"""
from __future__ import annotations

import subprocess
import sys
import time

CACHE_S = 30 * 60

_SCRIPT = (
    "Add-Type -AssemblyName System.Device;"
    "$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::Default);"
    "[void]$w.TryStart($false, [TimeSpan]::FromSeconds(5));"
    "for ($i = 0; $i -lt 20; $i++) { if (-not $w.Position.Location.IsUnknown) { break }; Start-Sleep -Milliseconds 500 };"
    "$p = $w.Position.Location; $w.Stop();"
    "if (-not $p.IsUnknown) { [string]::Format([cultureinfo]::InvariantCulture, '{0},{1}', $p.Latitude, $p.Longitude) }"
)

_cache: tuple[float, tuple[float, float]] | None = None


def parse(output: str) -> tuple[float, float] | None:
    try:
        lat, lon = (float(x) for x in output.strip().split(","))
    except ValueError:
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def here(run=subprocess.run, clock=time.monotonic) -> tuple[float, float] | None:
    """(latitude, longitude) from Windows, or None if unavailable (other OS, no permission, no signal)."""
    global _cache
    if _cache and clock() - _cache[0] < CACHE_S:
        return _cache[1]
    if sys.platform != "win32":
        return None
    try:
        proc = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                   capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = parse(proc.stdout)
    if found:
        _cache = (clock(), found)
    return found

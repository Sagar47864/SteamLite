"""OBS WebSocket 5.x request wrapper with reconnect-friendly error handling."""

from __future__ import annotations

from typing import Any


def _field(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


class ObsClient:
    """Queries OBS once every few seconds; callers reconnect after failures."""

    def __init__(self, host: str, port: int, password: str) -> None:
        self.host, self.port, self.password = host, port, password
        self._client: Any = None
        self._last_status: dict[str, Any] = {"connected": False}
        self._last_error = ""
        self._previous_counters: dict[str, tuple[float, float]] = {}

    def poll(self) -> dict[str, Any]:
        try:
            if self._client is None:
                try:
                    import obsws_python as obs
                except ImportError as exc:
                    raise RuntimeError("OBS support is unavailable. Install obsws-python.") from exc
                self._client = obs.ReqClient(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    timeout=0.6,
                )
            version = self._client.get_version()
            scene_response = self._client.get_current_program_scene()
            stream_response = self._client.get_stream_status()
            record_response = self._client.get_record_status()
            stats = self._client.get_stats()
            video = self._client.get_video_settings()

            stream_active = bool(_field(stream_response, "output_active", "outputActive", default=False))
            record_active = bool(_field(record_response, "output_active", "outputActive", default=False))
            rendering = self._interval_ratio(
                "rendering", stats,
                ("render_missed_frames", "renderMissedFrames"),
                ("render_total_frames", "renderTotalFrames"),
            )
            encoding = self._interval_ratio(
                "encoding", stats,
                ("output_skipped_frames", "outputSkippedFrames"),
                ("output_total_frames", "outputTotalFrames"),
            )
            network_drop = self._interval_ratio(
                "network",
                stream_response,
                ("output_skipped_frames", "outputSkippedFrames"),
                ("output_total_frames", "outputTotalFrames"),
            )
            bitrate = _field(stream_response, "output_bytes", "outputBytes")
            duration = _field(stream_response, "output_duration", "outputDuration")
            bitrate_kbps = None
            if bitrate is not None and duration:
                bitrate_kbps = float(bitrate) * 8 / max(float(duration), 1)  # duration is milliseconds; yields kb/s

            status = {
                "connected": True,
                "error": "",
                "obs_version": _field(version, "obs_version", "obsVersion", default=""),
                "scene": _field(scene_response, "current_program_scene_name", "currentProgramSceneName", default="Unavailable"),
                "streaming": stream_active,
                "recording": record_active,
                "stream_duration": _field(stream_response, "output_timecode", "outputTimecode", default="Unavailable"),
                "bitrate_kbps": bitrate_kbps,
                "network_dropped_percent": network_drop,
                "network_dropped_frames": _field(stream_response, "output_skipped_frames", "outputSkippedFrames") if stream_active else None,
                "rendering_lag_percent": rendering,
                "encoding_lag_percent": encoding,
                "width": _field(video, "output_width", "outputWidth"),
                "height": _field(video, "output_height", "outputHeight"),
                "fps_num": _field(video, "fps_numerator", "fpsNumerator"),
                "fps_den": _field(video, "fps_denominator", "fpsDenominator"),
                "active_fps": _field(stats, "active_fps", "activeFps"),
                "encoder": "Unavailable",
            }
            try:
                encoder_response = self._client.get_profile_parameter("Output", "Encoder")
                encoder = _field(encoder_response, "parameter_value", "parameterValue")
                if encoder:
                    status["encoder"] = encoder
            except Exception:
                try:
                    encoder_response = self._client.get_profile_parameter("Output", "StreamEncoder")
                    encoder = _field(encoder_response, "parameter_value", "parameterValue")
                    if encoder:
                        status["encoder"] = encoder
                except Exception:
                    pass
            self._last_status = status
            self._last_error = ""
            return status
        except Exception as exc:
            self._last_error = self._safe_error(exc)
            self.disconnect()
            self._last_status = {"connected": False, "error": self._last_error}
            return self._last_status

    def _interval_ratio(
        self,
        key: str,
        response: Any,
        numerator_names: tuple[str, ...],
        denominator_names: tuple[str, ...],
    ) -> float | None:
        numerator_raw = _field(response, *numerator_names)
        denominator_raw = _field(response, *denominator_names)
        if numerator_raw is None or denominator_raw is None:
            self._previous_counters.pop(key, None)
            return None
        numerator, denominator = float(numerator_raw), float(denominator_raw)
        previous = self._previous_counters.get(key)
        self._previous_counters[key] = (numerator, denominator)
        if previous is None or numerator < previous[0] or denominator < previous[1]:
            return None
        delta_total = denominator - previous[1]
        if delta_total <= 0:
            return None
        return max(0.0, numerator - previous[0]) / delta_total * 100

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc)
        # Avoid leaking any password should a library include a connection URL.
        if self.password:
            message = message.replace(self.password, "[redacted]")
        return message.replace("password", "credential").replace("Password", "Credential")[:240]

    def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

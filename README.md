# StreamLite

StreamLite is a local Windows desktop companion for monitoring system load while OBS Studio is running. Stream Mode samples the system once per second in a worker thread, optionally queries OBS WebSocket 5.x, reports conservative warnings, and stores a session summary in a local SQLite database. Monitoring remains available when OBS is not running.

The stability score is an approximate indicator based on the measurements available to StreamLite. It is not a scientific benchmark. StreamLite does not inject into games, change game files, disable Windows services, or automatically close processes.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- OBS Studio is optional. OBS WebSocket 5.x is built into OBS Studio 28 and later.

## Installation

Open PowerShell:

```powershell
cd "D:\New folder (3)\streamlite"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `py -3.11` is unavailable, replace it with the path to an installed Python 3.11+ interpreter. NVIDIA telemetry is optional and uses NVML through `nvidia-ml-py`; other GPUs show GPU metrics as unavailable. Temperature readings depend on hardware and driver support.

## Run

From the same activated PowerShell environment:

```powershell
python app.py
```

## OBS WebSocket setup

1. Open OBS Studio.
2. Open **Tools → WebSocket Server Settings**.
3. Enable the WebSocket server and keep it bound to the local machine. Do not expose it to the public internet.
4. Note the server port (default `4455`) and set a password in OBS.
5. In StreamLite, open **Settings** and enter host `127.0.0.1`, the port, and the password; select **Save settings**.
6. Start Stream Mode. StreamLite attempts to connect and retries if OBS starts later or reconnects.

The OBS password is stored through the Windows credential store via `keyring`. If secure storage is unavailable, StreamLite does not write the password to its regular settings; configure OBS without authentication only if that is suitable for your local setup.

## Configuration

Open **Settings** to change the OBS host and port, password, and optional game executable. Selecting a game executable makes detection match that process. Without one, automatic detection only recognizes a small set of known games when their process owns the foreground window. Unknown games can be selected manually.

**Always ignore** saves a process name in the local ignore list. **Ignore** applies for the current run. Closing a process requires confirmation; on Windows StreamLite sends a normal window-close request and does not force-terminate an app that does not close promptly. StreamLite refuses to close recognized Windows, security, driver, and service processes.

Game priority is optional. StreamLite records the original priority before applying Normal, Above Normal, or High, then attempts to restore it when Stream Mode stops. Realtime priority is never used.

## Stream Mode test procedure

1. Install dependencies and launch with the commands above.
2. Start the app with OBS closed. Select **START STREAM MODE**; CPU, RAM, disk, process, and network figures should populate within about one second. GPU and temperatures may show **Unavailable** if the hardware does not expose them.
3. Confirm the detected game is shown as `None` unless a configured or recognized game is in the foreground.
4. Start OBS, enable its WebSocket server, save the local host, port, and password in StreamLite Settings, then start Stream Mode again. Verify connection, scene, stream/record status, output size, FPS, bitrate, and OBS lag values when OBS provides them.
5. Start a stream to check the LIVE status. Stream network drops use the stream output's skipped/total frame counters; rendering and encoder lag use separate OBS stats counters.
6. Review process candidates. Choose **Close** and verify the confirmation prompt; choose **Cancel** to ensure no action occurs. Test **Ignore** and **Always ignore** to check that candidates disappear from the suggestions.
7. If a supported game is detected, optionally apply Above Normal priority. Stop Stream Mode and verify the original priority is restored.
8. Stop Stream Mode and open **History**. The completed session's averages, peaks, observed OBS network drops and peak lag percentages, and approximate stability score should be recorded locally.
9. With an incorrect OBS password or OBS stopped, verify system monitoring continues and OBS shows **Not connected**. Start OBS again and verify reconnection.

## Local data

Session history is stored in `streamlite.sqlite3` under the application-specific Windows Local App Data directory. Non-secret preferences are stored in Windows application settings. OBS passwords use Windows Credential Manager through the keyring package.

## Troubleshooting

- **OBS not connected:** Check OBS WebSocket is enabled, the host and port match, and the password is correct. StreamLite uses `127.0.0.1:4455` by default and retries automatically.
- **GPU unavailable:** NVML GPU utilization is available for supported NVIDIA drivers and devices. Non-NVIDIA GPUs and unavailable NVML readings are reported as unavailable, not as zero.
- **Temperature unavailable:** Many Windows hardware and driver combinations do not expose sensor readings to psutil.
- **Game shows None:** Set the executable in Settings. Automatic recognition is intentionally conservative and does not inspect or interact with anti-cheat software.
- **Priority change denied:** Windows may require the same or greater permissions as the game. StreamLite reports the failure and continues without changing priority.
- **Password could not be stored:** Confirm Windows Credential Manager is available. StreamLite avoids putting the password in its regular settings or logs.
- **Network frame drop unavailable:** OBS provides stream output frame counters only while the stream output is active. StreamLite leaves the measure unavailable when OBS has no active output counters rather than mislabeling rendering or encoder lag as network loss.

## PyInstaller packaging

Packaging is a separate build step and is not included in this implementation. The project uses Python modules and does not yet define or validate a Windows executable spec. Run directly with `python app.py` for now.

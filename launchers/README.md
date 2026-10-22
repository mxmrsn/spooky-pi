# Launchers: start Spooky Studio with a double-click

| Your computer | Start | Stop |
|---|---|---|
| **Windows** | `Start Spooky Studio.cmd` | `Stop Spooky Studio.cmd` |
| **Mac** | `Start Spooky Studio.command` | `Stop Spooky Studio.command` |
| **Linux** | `bash "Start Spooky Studio.command"` | `bash "Stop Spooky Studio.command"` |

**Start** connects to the Pi, starts the Studio if it isn't already running, and opens it in your browser. **Stop** frees the lights and speaker, for example before running the real show.

**The first time:**
- **Pi password:** a black window asks for it. Type it and press Enter; nothing shows while you type, which is normal. Ask the project team for the password.
- **Mac blocks the file:** if macOS says it's from an unidentified developer, right-click the file → **Open** → **Open**. You only need to do this once.

**If it can't connect:**
- **Is the Pi reachable?** Check that the Pi is switched on and your computer is on the same network.
- **Try the Pi's address:** some networks don't support `spooky-pi.local`. Open the launcher in a text editor and change `PI_HOST=spooky-pi.local` to the Pi's address, e.g. `PI_HOST=10.0.3.68`.

**What they run** (for the curious): `ssh spooky-pi@spooky-pi.local "bash ~/spooky/scripts/studio-ctl.sh start"`. The same script also takes `stop`, `restart`, `status` and `log`.

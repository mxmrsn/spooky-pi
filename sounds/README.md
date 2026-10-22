# Sounds

Put audio files (`.wav`, `.ogg` or `.mp3`) in these folders. The show picks a random file from the folder for each event, and avoids playing the same file twice in a row. An empty folder means that event is silent.

| Folder | When it plays |
|---|---|
| `ambient/` | Now and then while idle, every 45–120 s (`show.ambient_interval`) |
| `awaken/` | A PIR sensor wakes the show up |
| `countdown/` | The photo countdown starts (should last about 3 s) |
| `shutter/` | The photo is taken |
| `scream/` | The scary photo appears |

`.ogg` or `.wav` files at 44.1 kHz load the fastest. Keep them short, except for `ambient`.

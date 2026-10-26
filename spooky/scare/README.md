# Scary Smile

A static take on Snapchat's scary smile lens. It stretches the mouth into a wide upturned grin, enlarges and hollows the eyes, and applies a horror colour grade. Runs fully offline.

The show runs it on each photo (`spooky.scare.scare()`). It also works on its own, on photo files, once the package is installed (`pip install -e .` from the repo root). The face model `face_detection_yunet_2023mar.onnx` (OpenCV YuNet) ships in this folder.

## Usage

```
python -m spooky.scare photo.jpg
python -m spooky.scare photo.jpg -o out.png --grin 1.2 --eyes 0.4
python -m spooky.scare C:\path\to\folder
```

Output defaults to `<name>_scary.png` beside each input.

| Option | Effect |
|---|---|
| `--grin` | grin strength, 0 to 1.5 (default 1.0) |
| `--eyes` | eye enlargement, 0 to 0.6 (default 0.3) |
| `--no-hollow` | keep the natural eyes |
| `--no-grade` | skip the colour grade |

Images with no detectable face get the grade only. The exit code is 1 if any input could not be read or written.

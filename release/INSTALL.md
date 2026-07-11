# 3DpicToIFC — Installation Guide (Stage A release)

Turn a photo of a piece of furniture into a 3D model and a BIM-ready IFC
file, build rooms from a furniture catalog, and populate whole buildings —
all in your web browser, running locally on your own PC.

This is the **Stage A zip release**. A one-click installer (.exe) is coming
later; for now installation is three steps: install two free programs, run
`setup.bat` once, then run `start.bat` whenever you want to use the app.

---

## 1. What you need (prerequisites)

| Requirement | Details |
|---|---|
| Windows 10 or 11 | 64-bit |
| Node.js 20 LTS | Free. Download the "Windows Installer (.msi)" from <https://nodejs.org/en/download> and accept all defaults. |
| Python 3.11 or newer | Free. Download from <https://www.python.org/downloads/>. **Important:** on the first installer screen, tick **"Add python.exe to PATH"**. |
| Disk space | ~15 GB free (AI libraries and model weights are large). |
| Internet | Needed during setup and for the **first** 3D generation (model weights download once, then everything runs offline). |
| Graphics card (optional) | An NVIDIA GPU with **6 GB+ VRAM** is recommended — 3D generation takes seconds-to-a-minute. Without one the app still works on the CPU, but "High quality (TripoSR)" generation can take several minutes per photo. |

## 2. Install

1. Unzip this folder anywhere you like (e.g. `C:\3DpicToIFC`). Avoid
   OneDrive-synced folders if you can — they slow things down.
2. Double-click **`setup.bat`**. It will:
   - check Node.js and Python are installed (and tell you exactly what to
     do if they are not),
   - download the app's Node.js packages (~150 MB),
   - create a private Python environment in the `pyenv` folder and download
     the AI libraries (**several GB — 10 to 40 minutes**, one time only),
   - write the app's configuration file (`.env`),
   - optionally download segmentation weights (156 MB — if this fails, the
     app simply uses a built-in fallback).
3. When you see **"Setup complete — run start.bat"** you are done.

## 3. Run

1. Double-click **`start.bat`**.
2. Your browser opens <http://localhost:3000> automatically after a few
   seconds (if it does not, open that address yourself).
3. **Keep the black window open** — it is the app's engine and shows its
   log. Closing it stops the app.

## 4. First-run notes

- The **first time you generate a 3D model from a photo**, the app downloads
  its AI model weights from the internet (TripoSR ~1.5 GB, plus detection /
  classification / depth models — a few GB total). This happens **once**;
  the weights are cached on your PC and later runs work offline.
- The first generation is therefore slow. Later generations are much faster.
- This zip ships a **starter furniture catalog** (a small subset of the full
  ~4.8 GB ABO library). Catalog items without a bundled 3D mesh are shown
  and placed as correctly-sized simple shapes instead of detailed meshes.
- Everything runs locally. Photos and models never leave your PC (unless
  you configure the optional Meshy cloud API key).

## 5. Troubleshooting

**"Node.js is not installed" / "Python is not installed"**
Install them from the links in section 1, then run `setup.bat` again. If
you just installed them, close and reopen the setup window first (PATH
changes only apply to new windows).

**Port 3000 is already in use** (error like `EADDRINUSE: ... :3000`)
Another program (or a second copy of this app) is using port 3000. Close
the other program, or edit the `.env` file in this folder and change
`PORT=3000` to e.g. `PORT=3010`, then browse to `http://localhost:3010`.

**"Python script failed" or generation errors**
- Make sure `setup.bat` finished without errors (run it again — it is safe
  to re-run and resumes where it left off).
- The app uses the Python inside the `pyenv` folder (set via `PYTHON_PATH`
  in `.env`). If you moved the app folder, delete `.env` and the `pyenv`
  folder and run `setup.bat` again.

**First generation hangs or fails**
Usually the one-time model weight download — check your internet
connection and firewall/proxy (the app downloads from huggingface.co),
then try again.

**GPU vs CPU**
The app auto-detects an NVIDIA GPU (CUDA). With a 6 GB+ NVIDIA card,
high-quality generation takes seconds-to-a-minute. On CPU it still works
but can take several minutes per photo and uses a lower mesh resolution.
Keep your NVIDIA driver up to date.

**The browser opened before the app was ready**
Just press F5 (refresh) after a few seconds.

## 6. What's in the box

| Item | What it is |
|---|---|
| `setup.bat` | One-time installer (checks prerequisites, downloads packages). |
| `start.bat` | Starts the app and opens your browser. |
| `backend/` | The local server: Node.js API + Python AI pipeline (`backend/python-scripts/`) + vendored TripoSR. |
| `frontend/` | The web app you use in the browser (viewer, room builder, building tools). |
| `data/mesh_library_abo/` | Starter furniture catalog (subset of the CC-BY-4.0 Amazon Berkeley Objects library). |
| `sample_buildings/` | A sample architectural IFC (Duplex) for the building-population feature. |
| `requirements-app.txt` | Python package list used by `setup.bat`. |
| `pyenv/` (created by setup) | The app's private Python environment. |
| `.env` (created by setup) | App configuration (port, Python path, folders). |
| `outputs/`, `uploads/`, `temp/` | Your generated models and working files. |
| `licenses/`, `CREDITS.md` | Third-party licenses and attribution. |
| `INSTALL.md`, `RELEASE_NOTES_STAGE_A.md` | This guide and the release notes. |

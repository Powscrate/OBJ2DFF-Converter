# OBJ2DFF Converter

Convert Wavefront **OBJ** 3D models to **RenderWare DFF** (GTA III/VC/SA) with a built-in 3D previewer.

![GUI Screenshot](screenshot.png)

## Features

- **OBJ → DFF conversion** — Triangulates quads, computes bounding sphere, outputs valid RenderWare 3.4 clump
- **3D Preview** — Built-in PyOpenGL viewer with orbit controls, wireframe toggle, zoom
- **Open any DFF** — Preview existing DFF files without converting
- **TXD-ready** — Material exports with "untitled" texture reference; add your TXD later
- **Standalone .exe** — Bundled build runs on any Windows PC (no Python needed)

## Controls (3D Viewer)

| Action | Input |
|--------|-------|
| Rotate | Left-click + drag |
| Zoom   | Scroll wheel |
| Wireframe | W key |
| Reset camera | R key |
| Exit | ESC |

## Usage

### GUI (recommended)
```
Double-click OBJ2DFF_Converter.exe
```

### Command-line
```bash
python obj2dff.py input.obj output.dff
python obj2dff.py --view model.dff
```

## Requirements (for source)

- Python 3.10+
- `pip install customtkinter PyOpenGL PyOpenGL_accelerate pygame numpy`

## Build .exe yourself
```bash
pip install pyinstaller
pyinstaller --onedir --noconsole --name "OBJ2DFF_Converter" obj2dff.py
```

## License

MIT

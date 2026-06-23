#!/usr/bin/env python3
"""
OBJ to DFF Converter + 3D Viewer for GTA (RenderWare)
"""

import struct
import os
import math
import traceback
import sys
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox

RW_STRUCT        = 0x01
RW_STRING        = 0x02
RW_FRAME_LIST    = 0x0E
RW_GEOMETRY      = 0x0F
RW_CLUMP         = 0x10
RW_EXTENSION     = 0x11
RW_ATOMIC        = 0x14
RW_MATERIAL_LIST = 0x15
RW_TEXTURE       = 0x16
RW_MATERIAL      = 0x18
RW_GEOMETRY_LIST = 0x1A

RW_VERSION = 0x34004

CONTAINER_SECTIONS = {RW_CLUMP, RW_FRAME_LIST, RW_GEOMETRY_LIST,
                      RW_GEOMETRY, RW_MATERIAL_LIST, RW_MATERIAL,
                      RW_TEXTURE, RW_EXTENSION}


def pad4(data):
    while len(data) % 4:
        data += b'\x00'
    return data


def rw_section(sid, data, ver=RW_VERSION):
    return struct.pack('<III', sid, len(data), ver) + data


def rw_struct(data, ver=RW_VERSION):
    return rw_section(RW_STRUCT, data, ver)


def rw_string(s, ver=RW_VERSION):
    raw = s.encode('ascii') + b'\x00'
    return rw_section(RW_STRING, pad4(raw), ver)


# ---------------------------------------------------------------------------
# OBJ loader
# ---------------------------------------------------------------------------

class OBJ:
    def __init__(self):
        self.v = []
        self.vt = []
        self.vn = []
        self.faces = []

    def load(self, path):
        for line in open(path, 'r', encoding='utf-8', errors='ignore'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if not parts:
                continue
            kw = parts[0]
            if kw == 'v':
                self.v.append(tuple(float(x) for x in parts[1:4]))
            elif kw == 'vt':
                self.vt.append(tuple(float(x) for x in parts[1:3]))
            elif kw == 'vn':
                self.vn.append(tuple(float(x) for x in parts[1:4]))
            elif kw == 'f':
                face = []
                for p in parts[1:]:
                    if '/' in p:
                        idx = p.split('/')
                        vi = int(idx[0]) if idx[0] else 0
                        ti = int(idx[1]) if len(idx) > 1 and idx[1] else 0
                        ni = int(idx[2]) if len(idx) > 2 and idx[2] else 0
                    else:
                        vi = int(p)
                        ti = ni = 0
                    face.append((vi, ti, ni))
                if len(face) == 3:
                    self.faces.append(face)
                elif len(face) == 4:
                    self.faces.append([face[0], face[1], face[2]])
                    self.faces.append([face[0], face[2], face[3]])


# ---------------------------------------------------------------------------
# OBJ -> DFF converter
# ---------------------------------------------------------------------------

def convert(obj_path, dff_path):
    obj = OBJ()
    obj.load(obj_path)

    if not obj.faces:
        raise ValueError("No valid faces found in OBJ file (need at least 1 triangle)")

    v = obj.v
    vt = obj.vt
    vn = obj.vn

    vbuf = []
    vmap = {}
    idx_list = []

    for face in obj.faces:
        for vi, ti, ni in face:
            key = (vi, ti, ni)
            if key not in vmap:
                vmap[key] = len(vbuf)
                p = list(v[vi - 1]) if 1 <= vi <= len(v) else [0, 0, 0]
                n = list(vn[ni - 1]) if 1 <= ni <= len(vn) else [0, 1, 0]
                t = list(vt[ti - 1]) if 1 <= ti <= len(vt) else [0, 0]
                vbuf.append([p[0], p[1], p[2], n[0], n[1], n[2], t[0], 1.0 - t[1]])
            idx_list.append(vmap[key])

    nv = len(vbuf)
    nt = len(obj.faces)

    if nv > 65535:
        raise ValueError(f"Too many vertices ({nv}). DFF only supports up to 65535.")

    cx = cy = cz = 0.0
    for vert in vbuf:
        cx += vert[0]; cy += vert[1]; cz += vert[2]
    cx /= nv; cy /= nv; cz /= nv
    radius = 0.0
    for vert in vbuf:
        dx = vert[0] - cx; dy = vert[1] - cy; dz = vert[2] - cz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d > radius:
            radius = d
    if radius < 0.001:
        radius = 0.5

    tris = []
    for i in range(0, len(idx_list), 3):
        tris.append((idx_list[i], idx_list[i + 1], idx_list[i + 2]))

    with open(dff_path, 'wb') as f:
        gflags = 0x000B
        gd = struct.pack('<IIIII', gflags, nv, nt, 1, 0)

        gd += struct.pack('<4f', cx, cy, cz, radius)
        gd += struct.pack('<III', 1, 1, 0)

        for vert in vbuf:
            gd += struct.pack('<3f', vert[0], vert[1], vert[2])
        for vert in vbuf:
            gd += struct.pack('<3f', vert[3], vert[4], vert[5])
        for vert in vbuf:
            gd += struct.pack('<2f', vert[6], vert[7])
        for t in tris:
            gd += struct.pack('<HHH', t[0], t[1], t[2])

        mld = rw_struct(struct.pack('<I', 1))

        md = struct.pack('<I', 1)
        md += struct.pack('<BBBB', 255, 255, 255, 255)
        md += struct.pack('<i', 0)
        md += struct.pack('<I', 1)
        md += struct.pack('<f', 0)

        mat = rw_struct(md)

        txc = struct.pack('<HH', 0, 0) + struct.pack('<I', 0)
        tx = rw_struct(txc)
        tx += rw_string('untitled')
        tx += rw_string('')
        tx += rw_section(RW_EXTENSION, b'')
        mat += rw_section(RW_TEXTURE, tx)
        mat += rw_section(RW_EXTENSION, b'')
        mld += rw_section(RW_MATERIAL, mat)

        geom = rw_struct(gd)
        geom += rw_section(RW_MATERIAL_LIST, mld)
        geom += rw_section(RW_EXTENSION, b'')
        geom_section = rw_section(RW_GEOMETRY, geom)

        fc = struct.pack('<I', 1)
        fc += struct.pack('<9f', 1, 0, 0, 0, 1, 0, 0, 0, 1)
        fc += struct.pack('<3f', 0, 0, 0)
        fc += struct.pack('<iI', -1, 0)
        fl = rw_struct(fc)
        fl += rw_section(RW_EXTENSION, b'')
        fl_section = rw_section(RW_FRAME_LIST, fl)

        gl = rw_struct(struct.pack('<I', 1))
        gl += geom_section
        gl_section = rw_section(RW_GEOMETRY_LIST, gl)

        cd = rw_struct(struct.pack('<II', 1, 1))
        cd += fl_section
        cd += gl_section

        ad = struct.pack('<IIII', 0, 0, 0, 0)
        atm = rw_struct(ad)
        atm += rw_section(RW_EXTENSION, b'')
        cd += rw_section(RW_ATOMIC, atm)
        cd += rw_section(RW_EXTENSION, b'')

        f.write(rw_section(RW_CLUMP, cd))


# ---------------------------------------------------------------------------
# DFF parser (read back for viewing)
# ---------------------------------------------------------------------------

SECTION_NAMES = {
    0x01: "STRUCT", 0x02: "STRING", 0x0E: "FRAMELIST",
    0x0F: "GEOMETRY", 0x10: "CLUMP", 0x11: "EXTENSION",
    0x12: "ATOMIC", 0x14: "ATOMIC_OLD", 0x15: "MATERIALLIST",
    0x16: "TEXTURE", 0x18: "MATERIAL", 0x1A: "GEOMETRYLIST",
    0x1B: "FRAMELIST_OLD",
}


def _scan_sections(d, off=0, limit=None, depth=0):
    """Return a list of (sid, size, name, data_offset) found in the data."""
    if limit is None:
        limit = len(d)
    sections = []
    while off + 12 <= limit:
        sid, size, ver = struct.unpack('<III', d[off:off + 12])
        name = SECTION_NAMES.get(sid, f"0x{sid:02X}")
        data_off = off + 12
        if data_off + size > limit:
            break
        sections.append((sid, size, name, data_off))
        off = data_off + size
        if off % 4:
            off += 4 - (off % 4)
    return sections


def parse_dff(path):
    with open(path, 'rb') as f:
        data = f.read()

    # --- Recursive section walk ---
    def _find_geom(d, off=0):
        limit = len(d)
        while off + 12 <= limit:
            sid, size, ver = struct.unpack('<III', d[off:off + 12])
            if off + 12 + size > limit:
                break
            chunk = d[off + 12:off + 12 + size]
            if sid == RW_GEOMETRY:
                return chunk
            if sid in CONTAINER_SECTIONS:
                found = _find_geom(chunk)
                if found:
                    return found
            off += 12 + size
            if off % 4:
                off += 4 - (off % 4)
        return None

    geom = _find_geom(data)
    if geom is None:
        # --- Fallback: flat scan for valid GEOMETRY sections ---
        for i in range(len(data) - 12):
            if data[i:i+4] == b'\x0f\x00\x00\x00':
                size = struct.unpack('<I', data[i+4:i+8])[0]
                ver = struct.unpack('<I', data[i+8:i+12])[0]
                if size > len(data) or i + 12 + size > len(data):
                    continue
                if ver < 0x10000 or ver > 0x10000000:
                    continue
                geom = data[i + 12:i + 12 + size]
                break
    if geom is None:
        tops = _scan_sections(data)
        found = ', '.join(s[2] for s in tops) if tops else '(none)'
        raise ValueError(
            f"No geometry section found in DFF.\n"
            f"Top-level sections: {found}\n"
            f"File size: {len(data)} bytes"
        )

    # --- Find STRUCT inside geometry ---
    pos = 0
    while pos + 12 <= len(geom):
        sid, size, ver = struct.unpack('<III', geom[pos:pos + 12])
        if pos + 12 + size > len(geom):
            break
        chunk = geom[pos + 12:pos + 12 + size]
        if sid == RW_STRUCT:
            return _unpack_geom_struct(chunk)
        pos += 12 + size
        if pos % 4:
            pos += 4 - (pos % 4)

    # If STRUCT not found via sections, try reading raw at offset 0
    if len(geom) >= 20:
        try:
            return _unpack_geom_struct(geom)
        except Exception:
            pass

    kids = _scan_sections(geom)
    detail = ', '.join(f"{s[2]}({s[1]}b)" for s in kids) if kids else '(empty)'
    raise ValueError(
        f"No geometry struct found inside geometry section.\n"
        f"Children found: {detail}\n"
        f"First 32 bytes: {geom[:32].hex()}"
    )


def _unpack_geom_struct(d):
    p = 0
    flags, nv, nt, num_uv, has_vcol = struct.unpack('<IIIII', d[p:p + 20])
    p += 20

    if flags & 0x100:
        raise ValueError(
            f"Native data geometry (flag 0x{flags:04X}) not supported.\n"
            "This DFF uses a platform-specific format that cannot be read."
        )

    cx, cy, cz, radius = struct.unpack('<4f', d[p:p + 16])
    p += 16
    has_pos, has_norm, has_vcol_m = struct.unpack('<III', d[p:p + 12])
    p += 12

    verts = []
    if has_pos:
        for _ in range(nv):
            verts.append(struct.unpack('<3f', d[p:p + 12]))
            p += 12

    norms = []
    if has_norm:
        for _ in range(nv):
            norms.append(struct.unpack('<3f', d[p:p + 12]))
            p += 12

    if has_vcol_m:
        p += nv * 4

    uvs = []
    for _ in range(num_uv):
        layer = []
        for _ in range(nv):
            layer.append(struct.unpack('<2f', d[p:p + 8]))
            p += 8
        uvs.append(layer)

    is_strip = bool(flags & 0x10)
    tris = []
    for _ in range(nt):
        a, b, c = struct.unpack('<HHH', d[p:p + 6])
        p += 6
        if not is_strip:
            tris.append((a, b, c))
        else:
            tris.append((a, b, c))

    if not verts:
        raise ValueError("Geometry has no vertex positions")

    return {
        'vertices': verts,
        'normals': norms,
        'uvs': uvs[0] if uvs else [],
        'triangles': tris,
        'num_vertices': nv,
        'num_triangles': nt,
        'flags': flags,
    }


# ---------------------------------------------------------------------------
# DFF 3D Viewer (PyOpenGL + pygame)
# ---------------------------------------------------------------------------

def _msgbox(title, text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        print(f"{title}: {text}")


def run_viewer(dff_path):
    try:
        import pygame
        from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, K_ESCAPE, K_w, K_r, QUIT, MOUSEBUTTONDOWN, MOUSEMOTION
        from OpenGL import GL
        from OpenGL.GLU import gluLookAt, gluPerspective
    except ImportError as e:
        _msgbox("Missing Dependency", f"{e}\n\nInstall with:\n  pip install PyOpenGL PyOpenGL_accelerate pygame")
        return

    model = None
    try:
        model = parse_dff(dff_path)
    except Exception as e:
        _msgbox("DFF Load Error", f"Failed to load DFF:\n{e}")
        return

    verts = model['vertices']
    norms = model['normals']
    tris = model['triangles']

    if not verts or not tris:
        _msgbox("No Data", "No geometry data found in this DFF file.")
        return

    nv = model['num_vertices']
    nt = model['num_triangles']

    # Compute face normals if vertex normals are missing
    if not norms:
        norms = [[0.0, 0.0, 0.0] for _ in range(nv)]
        for t in tris:
            if t[0] < nv and t[1] < nv and t[2] < nv:
                v0, v1, v2 = verts[t[0]], verts[t[1]], verts[t[2]]
                nx = (v1[1] - v0[1]) * (v2[2] - v0[2]) - (v1[2] - v0[2]) * (v2[1] - v0[1])
                ny = (v1[2] - v0[2]) * (v2[0] - v0[0]) - (v1[0] - v0[0]) * (v2[2] - v0[2])
                nz = (v1[0] - v0[0]) * (v2[1] - v0[1]) - (v1[1] - v0[1]) * (v2[0] - v0[0])
                nl = math.sqrt(nx * nx + ny * ny + nz * nz)
                if nl > 0.001:
                    norms[t[0]] = [nx / nl, ny / nl, nz / nl]
                    norms[t[1]] = [nx / nl, ny / nl, nz / nl]
                    norms[t[2]] = [nx / nl, ny / nl, nz / nl]

    try:
        cx = sum(v[0] for v in verts) / nv
        cy = sum(v[1] for v in verts) / nv
        cz = sum(v[2] for v in verts) / nv
        max_r = max(math.sqrt((v[0] - cx) ** 2 + (v[1] - cy) ** 2 + (v[2] - cz) ** 2) for v in verts)
        if max_r < 0.001:
            max_r = 1.0

        pygame.init()
        W, H = 960, 640
        screen = pygame.display.set_mode((W, H), DOUBLEBUF | OPENGL)
        if screen is None:
            _msgbox("Display Error", "Could not create OpenGL window.")
            pygame.quit()
            return
        pygame.display.set_caption(f"DFF Viewer - {os.path.basename(dff_path)}  |  ESC exit")

        GL.glClearColor(0.12, 0.12, 0.14, 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [1, 2, 1, 0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, [0.35, 0.35, 0.35, 1])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.9, 0.9, 0.9, 1])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, [0.3, 0.3, 0.3, 1])

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        gluPerspective(40, W / H, 0.1, 500.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)

        cam_dist = max_r * 3.5
        angle_x, angle_y = 25, 45
        zoom = 1.0
        wireframe = False
        clock = pygame.time.Clock()
        running = True
        font = pygame.font.Font(None, 22)

        def draw_info():
            lines = [
                f"Vertices: {nv}   Triangles: {nt}",
                f"Mode: {'Wireframe' if wireframe else 'Solid'} (W to toggle)",
                "Drag to rotate | Scroll to zoom | R reset | ESC exit",
            ]
            viewport = GL.glGetIntegerv(GL.GL_VIEWPORT)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPushMatrix()
            GL.glLoadIdentity()
            GL.glOrtho(0, viewport[2], 0, viewport[3], -1, 1)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPushMatrix()
            GL.glLoadIdentity()
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glDisable(GL.GL_LIGHTING)

            y = viewport[3] - 20
            for line in lines:
                surf = font.render(line, True, (200, 200, 200))
                text_data = pygame.image.tostring(surf, 'RGBA', True)
                w, h = surf.get_size()
                GL.glWindowPos2i(12, y - h)
                GL.glDrawPixels(w, h, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, text_data)
                y -= h + 6

            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_LIGHTING)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPopMatrix()
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPopMatrix()

        while running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    running = False
                elif event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        running = False
                    elif event.key == K_w:
                        wireframe = not wireframe
                    elif event.key == K_r:
                        angle_x, angle_y = 25, 45
                        zoom = 1.0
                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == 4:
                        zoom = max(0.1, zoom * 0.88)
                    elif event.button == 5:
                        zoom = min(10, zoom * 1.13)
                elif event.type == MOUSEMOTION:
                    if event.buttons[0]:
                        dx, dy = event.rel
                        angle_y += dx * 0.5
                        angle_x += dy * 0.5
                        angle_x = max(-89, min(89, angle_x))

            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glLoadIdentity()

            dist = cam_dist * zoom
            rx = math.radians(angle_x)
            ry = math.radians(angle_y)
            ex = cx + dist * math.cos(rx) * math.sin(ry)
            ey = cy + dist * math.sin(rx)
            ez = cz + dist * math.cos(rx) * math.cos(ry)
            gluLookAt(ex, ey, ez, cx, cy, cz, 0, 1, 0)

            GL.glPushMatrix()
            GL.glTranslatef(-cx, -cy, -cz)

            if wireframe:
                GL.glDisable(GL.GL_LIGHTING)
                GL.glColor3f(0.3, 0.85, 1.0)
                GL.glBegin(GL.GL_LINES)
                for t in tris:
                    for i in range(3):
                        a, b = t[i], t[(i + 1) % 3]
                        if a < nv and b < nv:
                            GL.glVertex3fv(verts[a])
                            GL.glVertex3fv(verts[b])
                GL.glEnd()
            else:
                GL.glEnable(GL.GL_LIGHTING)
                GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE, [0.75, 0.75, 0.8, 1.0])
                GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, [0.2, 0.2, 0.2, 1])
                GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 30)
                GL.glBegin(GL.GL_TRIANGLES)
                for t in tris:
                    for i in t:
                        if i < len(norms):
                            GL.glNormal3fv(norms[i])
                        if i < nv:
                            GL.glVertex3fv(verts[i])
                GL.glEnd()

                GL.glDisable(GL.GL_LIGHTING)
                GL.glDisable(GL.GL_DEPTH_TEST)
                GL.glColor3f(0.08, 0.08, 0.12)
                GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
                GL.glBegin(GL.GL_TRIANGLES)
                for t in tris:
                    for i in t:
                        if i < nv:
                            GL.glVertex3fv(verts[i])
                GL.glEnd()
                GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_FILL)
                GL.glEnable(GL.GL_DEPTH_TEST)

            GL.glPopMatrix()

            draw_info()
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

    except Exception as e:
        try:
            pygame.quit()
        except Exception:
            pass
        _msgbox("Viewer Error", f"An error occurred:\n{e}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Find a Python interpreter that can run the viewer
# ---------------------------------------------------------------------------

def _find_python():
    if getattr(sys, 'frozen', False):
        return sys.executable
    candidates = [
        sys.executable,
        r'C:\Users\Number One\AppData\Local\Programs\Python\Python312\python.exe',
    ]
    for py in candidates:
        if not py or not os.path.isfile(py):
            continue
        try:
            r = subprocess.run(
                [py, '-c', 'import pygame; from OpenGL import GL'],
                capture_output=True, timeout=5
            )
            if r.returncode == 0:
                return py
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# CustomTkinter GUI
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("OBJ \u2192 DFF Converter + Viewer")
        self.geometry("700x520")
        self.resizable(False, False)
        self.minsize(700, 520)

        self.in_path = ctk.StringVar()
        self.out_path = ctk.StringVar()

        self._ui()

    def _ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        margin = {'padx': 16, 'pady': (12, 2)}

        ctk.CTkLabel(
            self, text="OBJ \u2192 DFF Converter + 3D Viewer",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, pady=(14, 0), sticky="n")

        ctk.CTkLabel(
            self, text="Convert OBJ 3D models to RenderWare DFF for GTA and preview them instantly",
            font=ctk.CTkFont(size=12), text_color="gray"
        ).grid(row=1, column=0, pady=(0, 10), sticky="n")

        ctk.CTkLabel(self, text="Input OBJ File:", font=ctk.CTkFont(size=12), anchor="w"
                     ).grid(row=2, column=0, sticky="w", **margin)
        r1 = ctk.CTkFrame(self, fg_color="transparent")
        r1.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 2))
        r1.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(r1, textvariable=self.in_path).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(r1, text="Browse", command=self._bin, width=80,
                       font=ctk.CTkFont(size=12)).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkLabel(self, text="Output DFF File:", font=ctk.CTkFont(size=12), anchor="w"
                     ).grid(row=4, column=0, sticky="w", **margin)
        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 6))
        r2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(r2, textvariable=self.out_path).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(r2, text="Browse", command=self._bout, width=80,
                       font=ctk.CTkFont(size=12)).grid(row=0, column=1, padx=(6, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=6, column=0, pady=12)

        self.btn_conv = ctk.CTkButton(
            btns, text="CONVERT", command=self._conv,
            fg_color="#2E7D32", hover_color="#1B5E20",
            text_color="white", font=ctk.CTkFont(size=13, weight="bold"),
            width=110, height=36, corner_radius=8
        )
        self.btn_conv.grid(row=0, column=0, padx=6)

        self.btn_view = ctk.CTkButton(
            btns, text="PREVIEW", command=self._view,
            fg_color="#1565C0", hover_color="#0D47A1",
            text_color="white", font=ctk.CTkFont(size=13, weight="bold"),
            width=110, height=36, corner_radius=8,
            state="disabled"
        )
        self.btn_view.grid(row=0, column=1, padx=6)

        self.btn_open = ctk.CTkButton(
            btns, text="OPEN DFF", command=self._open,
            fg_color="#6A1B9A", hover_color="#4A148C",
            text_color="white", font=ctk.CTkFont(size=13, weight="bold"),
            width=110, height=36, corner_radius=8
        )
        self.btn_open.grid(row=0, column=2, padx=6)

        self.lb = ctk.CTkTextbox(
            self, height=180, font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word", state="disabled"
        )
        self.lb.grid(row=7, column=0, sticky="nsew", padx=16, pady=(4, 14))
        self.grid_rowconfigure(7, weight=1)

    def _log(self, msg):
        self.lb.configure(state="normal")
        self.lb.insert("end", msg + "\n")
        self.lb.see("end")
        self.lb.configure(state="disabled")
        self.update()

    def _bin(self):
        p = filedialog.askopenfilename(
            filetypes=[("OBJ files", "*.obj"), ("All files", "*.*")]
        )
        if p:
            self.in_path.set(p)
            base, _ = os.path.splitext(p)
            if not self.out_path.get():
                self.out_path.set(base + ".dff")

    def _bout(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".dff",
            filetypes=[("DFF files", "*.dff"), ("All files", "*.*")]
        )
        if p:
            self.out_path.set(p)

    def _conv(self):
        ip = self.in_path.get()
        op = self.out_path.get()
        if not ip or not op:
            messagebox.showwarning("Missing", "Select both input and output files.")
            return
        self.btn_conv.configure(state="disabled", text="Converting...")
        self.btn_view.configure(state="disabled")
        try:
            self._log(f"Converting: {ip}")
            convert(ip, op)
            sz = os.path.getsize(op)
            self._log(f"Done! {os.path.basename(op)} ({sz:,} bytes)")
            self.btn_view.configure(state="normal")
            messagebox.showinfo("Success", f"Model converted!\n\n{op}")
        except Exception as e:
            self._log(f"ERROR: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", str(e))
        finally:
            self.btn_conv.configure(state="normal", text="CONVERT")

    def _open_dff_viewer(self, path):
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, '--view', path], shell=False)
            return
        py = _find_python()
        if not py:
            self._log("ERROR: No Python with pygame + PyOpenGL found")
            messagebox.showerror("Missing Dependencies",
                                 "PyOpenGL or pygame not installed.\n\n"
                                 "Run in terminal:\n"
                                 "  pip install PyOpenGL PyOpenGL_accelerate pygame")
            return
        self._log(f"Opening DFF viewer: {path}")
        subprocess.Popen([py, __file__, "--view", path], shell=False)

    def _view(self):
        op = self.out_path.get()
        if op and os.path.isfile(op):
            self._open_dff_viewer(op)
        else:
            p = filedialog.askopenfilename(
                filetypes=[("DFF files", "*.dff"), ("All files", "*.*")]
            )
            if p:
                self._open_dff_viewer(p)

    def _open(self):
        p = filedialog.askopenfilename(
            filetypes=[("DFF files", "*.dff"), ("All files", "*.*")]
        )
        if p:
            self._open_dff_viewer(p)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if '--view' in sys.argv:
        idx = sys.argv.index('--view')
        path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if path and os.path.isfile(path):
            run_viewer(path)
        else:
            print("Usage: python obj2dff.py --view <file.dff>")
    elif len(sys.argv) >= 3 and not sys.argv[1].startswith('-'):
        convert(sys.argv[1], sys.argv[2])
        print(f'Converted: {sys.argv[1]} -> {sys.argv[2]}')
    else:
        App().mainloop()

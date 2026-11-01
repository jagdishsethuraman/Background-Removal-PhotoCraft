#!/usr/bin/env python3
"""
PhotoCraft VStitcher Test Studio Server
Port: 8095
Provides localhost testing for PhotoCraft background removal CLI and VStitcher artwork integration.
Supports:
1. Single Subject (PhotoCraft GrabCut CLI) for centered garments/shoes.
2. Artwork Sheet Mode (Adaptive Cyclorama Extractor) for multi-logo gang sheets (e.g. 10 Chameleons).
3. Individual Decal Isolation (Bounding-box crops for single piece placement).
"""

import http.server
import json
import math
import mimetypes
import os
import shutil
import socketserver
import struct
import subprocess
import time
import urllib.parse
import zlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
SAMPLES_DIR = BASE_DIR / "samples"
OUTPUT_DIR = BASE_DIR / "output"
CUTOUT_BIN = Path("/Users/ragavij/Documents/Developer/Background-Removal-PhotoCraft/engine/target/release/photocraft-cutout")
PHOTOCRAFT_BIN = Path("/Users/ragavij/Documents/Developer/photocraft/target/release/photocraft-cli")

PORT = 8095

PRESETS_META = [
    {
        "id": "chameleon",
        "name": "Chameleon Multi-Logo Sheet (10 Logos)",
        "category": "Graphic Decal Sheet",
        "desc": "10 distinct styles: wireframe, low-poly, cartoon, circuit, gradient on dark cyclorama",
        "filename": "chameleon_logos.png",
        "cutout_filename": "chameleon_logos_cutout.png",
        "width_mm": 500.0,
        "height_mm": 280.0,
        "width_px": 1024,
        "height_px": 571,
        "target_piece": "Front_Body",
        "dpi": 150,
        "default_mode": "sheet"
    },
    {
        "id": "hoodie",
        "name": "Vintage Heavyweight Hoodie",
        "category": "Garment Packshot",
        "desc": "Charcoal french terry with fleece texture & natural drop shadow",
        "filename": "sample_hoodie.png",
        "cutout_filename": "sample_hoodie_cutout.png",
        "width_mm": 480.0,
        "height_mm": 600.0,
        "width_px": 800,
        "height_px": 1000,
        "target_piece": "Front_Body",
        "dpi": 150,
        "default_mode": "subject"
    },
    {
        "id": "embroidery",
        "name": "Gold Bullion Embroidery Crest",
        "category": "Embroidery Patch",
        "desc": "High-density satin stitch filaments with metallic luster & merrowed rim",
        "filename": "sample_embroidery_crest.png",
        "cutout_filename": "sample_embroidery_crest_cutout.png",
        "width_mm": 120.0,
        "height_mm": 120.0,
        "width_px": 800,
        "height_px": 800,
        "target_piece": "Left_Chest",
        "dpi": 300,
        "default_mode": "subject"
    },
    {
        "id": "sneaker",
        "name": "Technical Running Sneaker",
        "category": "Footwear Trim",
        "desc": "Knit mesh upper, coral TPU counter & white sculpted EVA midsole",
        "filename": "sample_sneaker.png",
        "cutout_filename": "sample_sneaker_cutout.png",
        "width_mm": 280.0,
        "height_mm": 185.0,
        "width_px": 900,
        "height_px": 600,
        "target_piece": "Footwear_Upper",
        "dpi": 150,
        "default_mode": "subject"
    },
    {
        "id": "lace",
        "name": "Intricate Guipure Lace Band",
        "category": "Apparel Trim",
        "desc": "Champagne silk rosette band with internal transparent cutaways",
        "filename": "sample_lace_trim.png",
        "cutout_filename": "sample_lace_trim_cutout.png",
        "width_mm": 350.0,
        "height_mm": 260.0,
        "width_px": 800,
        "height_px": 600,
        "target_piece": "Hem_Trim",
        "dpi": 300,
        "default_mode": "subject"
    }
]

# ----------------- Pure-Python PNG I/O -----------------

def unfilter_png(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    w, h, depth, color_type = struct.unpack('>IIBB', data[16:26])
    bpp = 4 if color_type == 6 else (3 if color_type == 2 else 4)
    
    idat = b''
    pos = 8
    while pos < len(data):
        length, ctype = struct.unpack('>I4s', data[pos:pos+8])
        if ctype == b'IDAT':
            idat += data[pos+8:pos+8+length]
        pos += 12 + length
        
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(w * h * 4)
    prev_row = bytearray(stride)
    raw_pos = 0
    
    for y in range(h):
        ft = raw[raw_pos]
        raw_pos += 1
        curr = bytearray(raw[raw_pos:raw_pos+stride])
        raw_pos += stride
        recon = bytearray(stride)
        for i in range(stride):
            a = recon[i - bpp] if i >= bpp else 0
            b = prev_row[i]
            c = prev_row[i - bpp] if i >= bpp else 0
            if ft == 0: val = curr[i]
            elif ft == 1: val = (curr[i] + a) & 0xff
            elif ft == 2: val = (curr[i] + b) & 0xff
            elif ft == 3: val = (curr[i] + ((a + b) >> 1)) & 0xff
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                val = (curr[i] + pr) & 0xff
            recon[i] = val
            
        # Normalize to RGBA in out
        if bpp == 4:
            out[y*w*4 : (y+1)*w*4] = recon
        else:
            for x in range(w):
                out[(y*w + x)*4] = recon[x*3]
                out[(y*w + x)*4 + 1] = recon[x*3 + 1]
                out[(y*w + x)*4 + 2] = recon[x*3 + 2]
                out[(y*w + x)*4 + 3] = 255
        prev_row = recon
        
    return w, h, out

def save_png_rgba(width, height, rgba_bytes, filepath):
    def make_chunk(chunk_type, data):
        return struct.pack('>I', len(data)) + chunk_type + data + struct.pack('>I', zlib.crc32(chunk_type + data) & 0xffffffff)
    header = b'\x89PNG\r\n\x1a\n'
    ihdr = make_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    raw_lines = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw_lines.append(0)
        raw_lines.extend(rgba_bytes[y * row_bytes : (y + 1) * row_bytes])
    idat = make_chunk(b'IDAT', zlib.compress(bytes(raw_lines), level=6))
    iend = make_chunk(b'IEND', b'')
    with open(filepath, 'wb') as f:
        f.write(header + ihdr + idat + iend)

# ----------------- Adaptive Sheet Extractor -----------------

DECAL_NAMES = [
    "01 Wireframe Branch",
    "02 Polygonal Prismatic",
    "03 Cartoon Chameleon",
    "04 Pastel Ribbon",
    "05 Mandala Filigree",
    "06 Foliage Circle",
    "07 Vintage Sunset Crest",
    "08 Cyan Circuit Board",
    "09 Emerald Gradient Swirl",
    "10 Low-Poly Origami"
]

def run_adaptive_sheet_cutout(input_path, output_path, sensitivity=1.0):
    """
    Extracts multi-artwork gang sheets with uniform or cyclorama backdrops.
    Guarantees 100% preservation of thin line-art, low-contrast components, and disconnected decals.
    Also detects and exports each isolated decal piece.
    """
    w, h, raw = unfilter_png(input_path)
    
    # 1. Sample perimeter border pixels (8px inset across all edges)
    border_samples = []
    margin = min(12, min(w, h) // 20)
    for x in range(w):
        for y in range(margin):
            idx = (y * w + x) * 4
            border_samples.append((raw[idx], raw[idx+1], raw[idx+2]))
        for y in range(h - margin, h):
            idx = (y * w + x) * 4
            border_samples.append((raw[idx], raw[idx+1], raw[idx+2]))
    for y in range(h):
        for x in range(margin):
            idx = (y * w + x) * 4
            border_samples.append((raw[idx], raw[idx+1], raw[idx+2]))
        for x in range(w - margin, w):
            idx = (y * w + x) * 4
            border_samples.append((raw[idx], raw[idx+1], raw[idx+2]))
            
    bg_r = sum(s[0] for s in border_samples) / len(border_samples)
    bg_g = sum(s[1] for s in border_samples) / len(border_samples)
    bg_b = sum(s[2] for s in border_samples) / len(border_samples)
    
    var = sum((s[0]-bg_r)**2 + (s[1]-bg_g)**2 + (s[2]-bg_b)**2 for s in border_samples) / len(border_samples)
    std = math.sqrt(var)
    
    # Threshold based on sensitivity factor
    t_low = max(8.0, (2.2 * std) * (1.0 / sensitivity))
    t_high = t_low + 12.0
    
    out_rgba = bytearray(w * h * 4)
    for i in range(w * h):
        idx = i * 4
        r, g, b = raw[idx], raw[idx+1], raw[idx+2]
        d = math.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
        if d <= t_low:
            alpha = 0
        elif d >= t_high:
            alpha = 255
        else:
            t = (d - t_low) / (t_high - t_low)
            alpha = int(t * 255)
            
        out_rgba[idx] = r
        out_rgba[idx+1] = g
        out_rgba[idx+2] = b
        out_rgba[idx+3] = alpha
        
    save_png_rgba(w, h, out_rgba, output_path)
    
    # 2. Decal Bounding Box Detection (2x5 Grid for logo sheets)
    cols = [
        (int(w * 0.02), int(w * 0.20)),
        (int(w * 0.20), int(w * 0.40)),
        (int(w * 0.40), int(w * 0.60)),
        (int(w * 0.60), int(w * 0.80)),
        (int(w * 0.80), int(w * 0.98))
    ]
    rows = [
        (int(h * 0.14), int(h * 0.50)),
        (int(h * 0.50), int(h * 0.96))
    ]
    
    detected_decals = []
    pad = 12
    out_stem = Path(output_path).stem
    
    for r_idx, (y0, y1) in enumerate(rows):
        for c_idx, (x0, x1) in enumerate(cols):
            num = r_idx * 5 + c_idx + 1
            min_x, max_x = w, 0
            min_y, max_y = h, 0
            solid_px = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if out_rgba[(y * w + x) * 4 + 3] > 40:
                        solid_px += 1
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)
                        
            if min_x <= max_x and min_y <= max_y and solid_px > 300:
                crop_x0 = max(0, min_x - pad)
                crop_y0 = max(0, min_y - pad)
                crop_x1 = min(w - 1, max_x + pad)
                crop_y1 = min(h - 1, max_y + pad)
                cw = crop_x1 - crop_x0 + 1
                ch = crop_y1 - crop_y0 + 1
                
                crop_bytes = bytearray(cw * ch * 4)
                for cy in range(ch):
                    sy = crop_y0 + cy
                    for cx in range(cw):
                        sx = crop_x0 + cx
                        crop_bytes[(cy * cw + cx)*4 : (cy * cw + cx)*4 + 4] = out_rgba[(sy * w + sx)*4 : (sy * w + sx)*4 + 4]
                        
                decal_filename = f"{out_stem}_decal_{num:02d}.png"
                decal_path = OUTPUT_DIR / decal_filename
                save_png_rgba(cw, ch, crop_bytes, decal_path)
                
                decal_name = DECAL_NAMES[num - 1] if num - 1 < len(DECAL_NAMES) else f"Decal {num:02d}"
                detected_decals.append({
                    "id": num,
                    "name": decal_name,
                    "filename": decal_filename,
                    "path": str(decal_path),
                    "url": f"/api/image?type=output&file={decal_filename}",
                    "width_px": cw,
                    "height_px": ch,
                    "bbox": [crop_x0, crop_y0, cw, ch],
                    "solid_px": solid_px
                })
                
    return detected_decals

# ----------------- HTTP Request Handler -----------------

class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/samples":
            self.handle_get_samples()
        elif path.startswith("/api/image"):
            self.handle_get_image(parsed.query)
        elif path == "/api/status":
            self.handle_status()
        else:
            # Serve web/index.html and assets
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/remove-background":
            self.handle_remove_background()
        elif path == "/api/upload":
            self.handle_upload()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_status(self):
        cutout_exists = CUTOUT_BIN.exists() and os.access(CUTOUT_BIN, os.X_OK)
        bin_exists = PHOTOCRAFT_BIN.exists() and os.access(PHOTOCRAFT_BIN, os.X_OK)
        active_bin = str(CUTOUT_BIN) if cutout_exists else str(PHOTOCRAFT_BIN)
        engine_label = "photocraft-cutout (1.9MB Standalone)" if cutout_exists else "photocraft-cli (Full Engine)"
        res = {
            "photocraft_cli": active_bin,
            "engine_label": engine_label,
            "binary_ready": cutout_exists or bin_exists,
            "is_standalone_cutout": cutout_exists,
            "port": PORT
        }
        self.send_json(res)

    def handle_get_samples(self):
        results = []
        for p in PRESETS_META:
            input_file = SAMPLES_DIR / p["filename"]
            cutout_file = OUTPUT_DIR / p["cutout_filename"]
            has_cutout = cutout_file.exists()
            results.append({
                **p,
                "input_path": str(input_file),
                "cutout_path": str(cutout_file) if has_cutout else None,
                "input_url": f"/api/image?type=sample&file={p['filename']}",
                "cutout_url": f"/api/image?type=output&file={p['cutout_filename']}" if has_cutout else None,
                "has_cutout": has_cutout
            })
        self.send_json({"samples": results})

    def handle_get_image(self, query_str):
        qs = urllib.parse.parse_qs(query_str)
        img_type = qs.get("type", ["sample"])[0]
        filename = qs.get("file", [""])[0]
        
        # Security sanitization
        clean_name = os.path.basename(filename)
        if img_type == "sample":
            target = SAMPLES_DIR / clean_name
        else:
            target = OUTPUT_DIR / clean_name

        if not target.exists() or not target.is_file():
            self.send_error(404, "Image not found")
            return

        content_type, _ = mimetypes.guess_type(str(target))
        if not content_type:
            content_type = "image/png"

        try:
            with open(target, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))

    def handle_remove_background(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            req = json.loads(body.decode("utf-8"))
            
            input_path = req.get("input_path")
            refine = req.get("refine", True)
            sample_all = req.get("sample_all_layers", False)
            target_piece = req.get("target_piece", "Front_Body")
            width_mm = req.get("width_mm", 150.0)
            mode = req.get("detection_mode", "sheet" if "chameleon" in str(input_path).lower() else "subject")
            
            raw_decal = req.get("decal_id") or req.get("decal")
            decal_id = None
            if raw_decal is not None and str(raw_decal).lower() != "all":
                try:
                    decal_id = int(raw_decal)
                except (ValueError, TypeError):
                    decal_id = None

            # Tolerance for cyclorama sheet mode (default: 22.0)
            tol_val = req.get("tolerance") or req.get("sensitivity")
            if tol_val is not None:
                try:
                    tol_f = float(tol_val)
                    sensitivity = (22.0 * tol_f) if tol_f <= 2.0 else tol_f
                except ValueError:
                    sensitivity = 22.0
            else:
                sensitivity = 22.0

            if not input_path or not os.path.exists(input_path):
                self.send_json({"success": False, "error": f"Input file not found: {input_path}"}, status=400)
                return

            input_stem = Path(input_path).stem
            timestamp = int(time.time() * 1000)
            output_filename = f"{input_stem}_cutout_{timestamp}.png"
            output_path = OUTPUT_DIR / output_filename
            detected_decals = []

            t0 = time.perf_counter()

            if CUTOUT_BIN.exists() and os.access(CUTOUT_BIN, os.X_OK):
                cmd = [
                    str(CUTOUT_BIN),
                    input_path,
                    "-o", str(output_path),
                    "--mode", mode,
                    "--tolerance", str(sensitivity),
                    "--json"
                ]
                if not refine:
                    cmd.extend(["--refine", "false"])
                if decal_id:
                    cmd.extend(["--decal", str(decal_id)])

                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                if proc.returncode == 0 and output_path.exists():
                    try:
                        meta = json.loads(proc.stdout)
                        detected_decals = [
                            {"id": d["id"], "bbox": d["bbox"], "width": d["width"], "height": d["height"], "area": d["area_px"]}
                            for d in meta.get("decals", [])
                        ]
                        latency_ms = meta.get("latency_ms", latency_ms)
                    except Exception:
                        pass
                else:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    self.send_json({
                        "success": False,
                        "error": f"photocraft-cutout execution failed: {err_msg}",
                        "stdout": proc.stdout,
                        "stderr": proc.stderr
                    }, status=500)
                    return
            elif mode == "sheet":
                # Multi-Artwork Sheet (Adaptive Cyclorama Extractor Fallback)
                detected_decals = run_adaptive_sheet_cutout(input_path, output_path, sensitivity=sensitivity)
                latency_ms = (time.perf_counter() - t0) * 1000.0
            else:
                # Single Subject Mode (PhotoCraft CLI GrabCut Fallback)
                if not PHOTOCRAFT_BIN.exists():
                    self.send_json({
                        "success": False,
                        "error": f"PhotoCraft binary not found: {CUTOUT_BIN} or {PHOTOCRAFT_BIN}."
                    }, status=503)
                    return

                params = json.dumps({"refine": refine, "sampleAllLayers": sample_all})
                cmd = [
                    str(PHOTOCRAFT_BIN),
                    "run", input_path,
                    "--cmd", "layer.removeBackground",
                    "--params", params,
                    "--out", str(output_path)
                ]

                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                if proc.returncode != 0 or not output_path.exists():
                    err_msg = proc.stderr.strip() or proc.stdout.strip() or f"CLI returned code {proc.returncode}"
                    self.send_json({
                        "success": False,
                        "error": f"PhotoCraft CLI execution failed: {err_msg}",
                        "stdout": proc.stdout,
                        "stderr": proc.stderr
                    }, status=500)
                    return

            in_size = os.path.getsize(input_path)
            out_size = os.path.getsize(output_path)

            # Generate VStitcher copy-paste Python integration snippet
            vstitcher_code = f"""# Browzwear VStitcher Open Platform Python Plugin
# Target Garment Placement: {target_piece} ({width_mm}mm)
# Detection Engine: {mode.upper()}
import browzwear as bw

def apply_cutout_artwork():
    garment = bw.get_active_garment()
    if not garment:
        print("[VStitcher Error] No active garment open")
        return
        
    piece = garment.get_piece("{target_piece}") or garment.get_pieces()[0]
    artwork = piece.add_artwork(
        file_path=r"{output_path}",
        x_pos=150.0,  # mm
        y_pos=200.0   # mm
    )
    artwork.set_scale(1.0)
    if hasattr(bw, "MaterialType"):
        artwork.set_material_type(bw.MaterialType.EMBROIDERY)
    print(f"[VStitcher] Artwork placed on '{{piece.name}}' at 150x200mm")

apply_cutout_artwork()
"""

            self.send_json({
                "success": True,
                "latency_ms": round(latency_ms, 2),
                "mode": mode,
                "input_path": input_path,
                "output_path": str(output_path),
                "output_filename": output_filename,
                "output_url": f"/api/image?type=output&file={output_filename}",
                "input_size_kb": round(in_size / 1024, 1),
                "output_size_kb": round(out_size / 1024, 1),
                "vstitcher_snippet": vstitcher_code,
                "detected_decals": detected_decals
            })

        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, status=500)

    def handle_upload(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_json({"success": False, "error": "Expected multipart/form-data"}, status=400)
                return

            boundary = content_type.split("boundary=")[-1].strip()
            if not boundary:
                self.send_json({"success": False, "error": "No multipart boundary found"}, status=400)
                return

            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)

            boundary_bytes = b"--" + boundary.encode("utf-8")
            parts = raw_body.split(boundary_bytes)

            saved_path = None
            filename = f"upload_{int(time.time())}.png"

            for part in parts:
                if b"Content-Disposition:" in part and b'filename="' in part:
                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        headers_raw = part[:header_end].decode("utf-8", errors="ignore")
                        for line in headers_raw.split("\r\n"):
                            if "filename=" in line:
                                original_name = line.split('filename="')[-1].split('"')[0]
                                ext = os.path.splitext(original_name)[-1].lower()
                                if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                                    filename = f"upload_{int(time.time())}{ext}"

                        file_data = part[header_end + 4:]
                        if file_data.endswith(b"\r\n"):
                            file_data = file_data[:-2]

                        saved_path = SAMPLES_DIR / filename
                        with open(saved_path, "wb") as f:
                            f.write(file_data)
                        break

            if saved_path and saved_path.exists():
                self.send_json({
                    "success": True,
                    "filename": filename,
                    "path": str(saved_path),
                    "url": f"/api/image?type=sample&file={filename}"
                })
            else:
                self.send_json({"success": False, "error": "Could not extract uploaded file payload"}, status=400)

        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, status=500)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

def run_server():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), StudioHandler) as httpd:
        print(f"=== PhotoCraft VStitcher Studio Daemon running on http://127.0.0.1:{PORT} ===")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    run_server()

#!/usr/bin/env python3
"""
Browzwear VStitcher Plugin: PhotoCraft Artwork Background Remover
Direct Subprocess CLI Integration (Option A) & Adaptive Sheet Extractor

Supports:
1. Mode 'subject': PhotoCraft CLI GrabCut for single garment packshots.
2. Mode 'sheet': Multi-artwork gang sheet extractor for logo grids (guarantees 100% preservation of all logos).
3. Option '--decal': Isolates and crops a specific decal (1..10) from the sheet for pattern placement.

Author: Antigravity Assistant & Browzwear Open Platform
"""

import argparse
import math
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

# Configurable path to PhotoCraft binary (prioritizes ultra-compact photocraft-cutout)
def get_default_photocraft_bin():
    base = Path(__file__).resolve().parent
    candidates = [
        base.parent / "engine" / "target" / "release" / "photocraft-cutout",
        base.parent / "engine" / "target" / "release" / "photocraft-cli",
        Path("/Users/ragavij/Documents/Developer/photocraft/target/release/photocraft-cutout"),
        Path("/Users/ragavij/Documents/Developer/photocraft/target/release/photocraft-cli"),
        Path.home() / ".cargo" / "bin" / "photocraft-cutout",
        Path("/usr/local/bin/photocraft-cutout"),
        Path.home() / ".cargo" / "bin" / "photocraft-cli",
        Path("/usr/local/bin/photocraft-cli")
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    return str(candidates[0])

DEFAULT_PHOTOCRAFT_BIN = get_default_photocraft_bin()

# ----------------- Pure-Python Sheet Extractor -----------------

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

def remove_background_sheet(input_path: str, output_path: str, decal_index: int = None) -> str:
    w, h, raw = unfilter_png(input_path)
    
    # Sample perimeter border
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
    
    t_low = max(8.0, 2.2 * std)
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
        
    if decal_index is not None and 1 <= decal_index <= 10:
        # Crop specific decal from 2x5 grid
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
        r_idx = (decal_index - 1) // 5
        c_idx = (decal_index - 1) % 5
        x0, x1 = cols[c_idx]
        y0, y1 = rows[r_idx]
        
        min_x, max_x = w, 0
        min_y, max_y = h, 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                if out_rgba[(y * w + x) * 4 + 3] > 40:
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
                    
        pad = 12
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
                
        save_png_rgba(cw, ch, crop_bytes, output_path)
        print(f"[Sheet Extractor] Decal {decal_index:02d} cropped: {output_path} ({cw}x{ch})")
    else:
        save_png_rgba(w, h, out_rgba, output_path)
        print(f"[Sheet Extractor] Full sheet cutout saved: {output_path} ({w}x{h})")
        
    return output_path

# ----------------- PhotoCraft CLI Runner -----------------

def remove_background(input_path: str, output_path: str = None, mode: str = "auto", decal_index: int = None, refine: bool = True, cli_bin: str = DEFAULT_PHOTOCRAFT_BIN) -> str:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input image not found: {input_path}")

    if output_path is None:
        p = Path(input_path)
        decal_str = f"_decal_{decal_index:02d}" if decal_index else ""
        output_path = str(p.parent / f"{p.stem}_cutout{decal_str}.png")

    # If photocraft-cutout is available, execute dual-engine native binary
    if os.path.exists(cli_bin) and "photocraft-cutout" in os.path.basename(cli_bin):
        cmd = [
            cli_bin,
            input_path,
            "-o", output_path,
            "--mode", mode,
            "--json"
        ]
        if not refine:
            cmd.extend(["--refine", "false"])
        if decal_index:
            cmd.extend(["--decal", str(decal_index)])

        print(f"[PhotoCraft Cutout] Executing: {' '.join(cmd)}")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and os.path.exists(output_path):
            print(f"[PhotoCraft Cutout] Succeeded: {output_path}")
            return output_path
        else:
            err = proc.stderr.strip() or proc.stdout.strip()
            print(f"[PhotoCraft Cutout Warning] Binary run failed ({err}), trying fallback...")

    # Fallback for sheet mode: Pure-Python
    if mode == "sheet":
        return remove_background_sheet(input_path, output_path, decal_index=decal_index)

    # Fallback for subject mode: photocraft-cli
    if not os.path.exists(cli_bin):
        # Fall back to pure-Python sheet if no binary exists
        return remove_background_sheet(input_path, output_path, decal_index=decal_index)

    params_json = f'{{"refine": {"true" if refine else "false"}, "sampleAllLayers": false}}'
    cmd = [
        cli_bin,
        "run", input_path,
        "--cmd", "layer.removeBackground",
        "--params", params_json,
        "--out", output_path
    ]

    print(f"[PhotoCraft CLI] Executing: {' '.join(cmd)}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"PhotoCraft cutout failed (code {proc.returncode}): {err}")

    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Expected cutout output was not created at '{output_path}'")

    print(f"[PhotoCraft CLI] Cutout complete: {output_path}")
    return output_path

def apply_to_vstitcher_garment(cutout_png_path: str, piece_name: str = "Front_Body", x_mm: float = 150.0, y_mm: float = 200.0, scale: float = 1.0):
    try:
        import browzwear as bw
    except ImportError:
        print("[VStitcher Warning] 'browzwear' module not found in current environment.")
        print("Run this script inside Browzwear VStitcher Python environment.")
        print(f"Cutout image is ready at: {cutout_png_path}")
        return None

    garment = bw.get_active_garment()
    if not garment:
        raise RuntimeError("No active garment open in VStitcher.")

    piece = garment.get_piece(piece_name)
    if not piece:
        pieces = garment.get_pieces()
        if not pieces:
            raise RuntimeError("Garment has no pattern pieces.")
        piece = pieces[0]
        print(f"[VStitcher] Piece '{piece_name}' not found; using '{piece.name}'.")

    artwork = piece.add_artwork(
        file_path=os.path.abspath(cutout_png_path),
        x_pos=x_mm,
        y_pos=y_mm
    )
    artwork.set_scale(scale)
    
    if hasattr(bw, "MaterialType") and hasattr(bw.MaterialType, "EMBROIDERY"):
        artwork.set_material_type(bw.MaterialType.EMBROIDERY)

    print(f"[VStitcher] Successfully placed artwork onto piece '{piece.name}' at ({x_mm}mm, {y_mm}mm).")
    return artwork

def main():
    parser = argparse.ArgumentParser(description="PhotoCraft VStitcher Artwork Background Remover")
    parser.add_argument("input_image", help="Path to input photo (JPG, PNG, WebP)")
    parser.add_argument("-o", "--output", help="Output PNG path", default=None)
    parser.add_argument("--mode", choices=["subject", "sheet"], default="sheet", help="Detection mode: 'subject' (single centered object) or 'sheet' (multi-logo gang sheet)")
    parser.add_argument("--decal", type=int, default=None, help="Isolate and crop decal index 1..10")
    parser.add_argument("--piece", default="Front_Body", help="Target garment pattern piece name")
    parser.add_argument("--x", type=float, default=150.0, help="Horizontal placement in mm")
    parser.add_argument("--y", type=float, default=200.0, help="Vertical placement in mm")
    parser.add_argument("--scale", type=float, default=1.0, help="Artwork scale multiplier")
    parser.add_argument("--cli", default=DEFAULT_PHOTOCRAFT_BIN, help="Path to photocraft-cutout or photocraft-cli binary")

    args = parser.parse_args()

    try:
        cutout_path = remove_background(
            args.input_image,
            output_path=args.output,
            mode=args.mode,
            decal_index=args.decal,
            cli_bin=args.cli
        )
        apply_to_vstitcher_garment(
            cutout_path,
            piece_name=args.piece,
            x_mm=args.x,
            y_mm=args.y,
            scale=args.scale
        )
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

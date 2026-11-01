#!/usr/bin/env python3
"""
Pure Python PNG generator (zero external dependencies).
Generates test samples for PhotoCraft background removal.
"""

import math
import os
import struct
import zlib

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def save_png(filename, width, height, pixels_rgb):
    """Save an RGB image as PNG with zero external dependencies."""
    # PNG signature
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    
    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    png += struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    
    # IDAT chunk (scanlines with filter byte 0)
    raw_bytes = bytearray()
    for y in range(height):
        raw_bytes.append(0) # Filter: None
        row_start = y * width * 3
        raw_bytes.extend(pixels_rgb[row_start:row_start + width * 3])
        
    compressed = zlib.compress(bytes(raw_bytes), level=6)
    idat_crc = zlib.crc32(b'IDAT' + compressed)
    png += struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
    
    # IEND chunk
    iend_crc = zlib.crc32(b'IEND')
    png += struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    
    with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
        f.write(png)
    print(f"Created {filename}")

def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        p1x, p1y = poly[i]
        p2x, p2y = poly[(i + 1) % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
    return inside

def generate_tshirt():
    w, h = 600, 750
    buf = bytearray()
    
    poly = [
        (250, 110), (350, 110), (470, 160), (540, 280),
        (480, 310), (430, 250), (420, 580), (180, 580),
        (170, 250), (120, 310), (60, 280), (130, 160)
    ]
    
    for y in range(h):
        for x in range(w):
            # Check collar cutout
            in_body = point_in_poly(x, y, poly)
            # Collar oval cutout
            dx = (x - 300) / 50.0
            dy = (y - 110) / 30.0
            in_collar = (dx*dx + dy*dy <= 1.0) and (y >= 110)
            
            if in_body and not in_collar:
                # Navy garment color with subtle fabric gradient
                r = int(24 + (y / h) * 15)
                g = int(38 + (y / h) * 20)
                b = int(72 + (y / h) * 30)
                
                # Chest logo wave
                if 280 <= y <= 320 and 230 <= x <= 370:
                    wave_y = 300 + 15 * math.sin((x - 230) * 0.05)
                    if abs(y - wave_y) < 8:
                        r, g, b = 245, 180, 45 # Gold print
                buf.extend([r, g, b])
            else:
                # Clean studio off-white backdrop
                bg = 248 if ((x + y) % 4 == 0) else 246
                buf.extend([bg, bg, bg + 1])
                
    save_png("sample_tshirt.png", w, h, buf)

def generate_embroidery():
    w, h = 600, 600
    buf = bytearray()
    cx, cy = 300, 300
    radius = 180
    
    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist <= radius:
                if dist > radius - 16:
                    # Gold merrowed border
                    buf.extend([225, 175, 30])
                elif dist > radius - 20:
                    # Shadow groove
                    buf.extend([120, 90, 15])
                else:
                    # Black twill base with embroidered cross
                    angle = (math.atan2(dy, dx) + math.pi) % (math.pi / 2)
                    if abs(dx) < 25 or abs(dy) < 25:
                        buf.extend([240, 240, 245]) # White satin stitch
                    elif abs(dx) < 32 or abs(dy) < 32:
                        buf.extend([210, 40, 40])   # Red accent
                    else:
                        buf.extend([20, 22, 28])    # Charcoal twill
            else:
                # Warm studio backdrop
                buf.extend([236, 233, 228])
                
    save_png("sample_embroidery.png", w, h, buf)

def generate_trim():
    w, h = 700, 450
    buf = bytearray()
    
    sneaker_poly = [
        (100, 340), (200, 345), (380, 345), (550, 340), (620, 320),
        (610, 280), (530, 290), (360, 295), (170, 295), (95, 315)
    ]
    upper_poly = [
        (95, 315), (170, 295), (250, 240), (370, 195), (420, 195),
        (450, 225), (530, 290), (610, 280), (580, 250), (480, 160),
        (380, 145), (300, 180), (220, 235), (135, 280), (95, 315)
    ]
    
    for y in range(h):
        for x in range(w):
            in_sole = point_in_poly(x, y, sneaker_poly)
            in_upper = point_in_poly(x, y, upper_poly)
            
            if in_sole:
                buf.extend([255, 255, 255]) # Pure white EVA midsole
            elif in_upper:
                # Cyan upper with coral stripe
                if 200 <= x <= 460 and 200 <= y <= 270:
                    diag = (x - 200) * 0.35 + (y - 200)
                    if 40 <= diag <= 65:
                        buf.extend([244, 63, 94]) # Coral
                    else:
                        buf.extend([14, 165, 233]) # Electric Cyan
                else:
                    buf.extend([14, 165, 233])
            else:
                buf.extend([244, 245, 248]) # Neutral background
                
    save_png("sample_trim.png", w, h, buf)

if __name__ == "__main__":
    generate_tshirt()
    generate_embroidery()
    generate_trim()

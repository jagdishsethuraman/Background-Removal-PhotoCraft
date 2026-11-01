#!/usr/bin/env python3
"""
Photorealistic Fashion & Embroidery Sample Generator (Zero External Dependencies).
Synthesizes photo-grade apparel packshots with natural lighting, fabric noise,
and anti-aliased silhouettes for Browzwear VStitcher cutout testing.
"""

import math
import os
import random
import struct
import zlib

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def save_png_rgba(filename, width, height, pixels_rgba):
    """Save 32-bit RGBA PNG."""
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    png += struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr))
    
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row_start = y * width * 4
        raw.extend(pixels_rgba[row_start:row_start + width * 4])
        
    comp = zlib.compress(bytes(raw), level=6)
    png += struct.pack('>I', len(comp)) + b'IDAT' + comp + struct.pack('>I', zlib.crc32(b'IDAT' + comp))
    png += struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND'))
    
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, 'wb') as f:
        f.write(png)
    print(f"Generated: {path}")

def save_png_rgb(filename, width, height, pixels_rgb):
    """Save 24-bit RGB PNG."""
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png += struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr))
    
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row_start = y * width * 3
        raw.extend(pixels_rgb[row_start:row_start + width * 3])
        
    comp = zlib.compress(bytes(raw), level=6)
    png += struct.pack('>I', len(comp)) + b'IDAT' + comp + struct.pack('>I', zlib.crc32(b'IDAT' + comp))
    png += struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND'))
    
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, 'wb') as f:
        f.write(png)
    print(f"Generated: {path}")

def point_in_polygon(x, y, poly):
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

# -------------------------------------------------------------
# 1. Vintage Heavyweight Hoodie Packshot
# -------------------------------------------------------------
def make_hoodie():
    w, h = 800, 1000
    pixels = bytearray(w * h * 3)
    random.seed(42)

    # Hoodie silhouette nodes
    hoodie_poly = [
        (320, 140), (480, 140), # hood crown
        (540, 200), (660, 280), # right shoulder
        (760, 480),             # right sleeve wrist
        (690, 520),             # right cuff inner
        (590, 390),             # right armpit
        (580, 830),             # right hem
        (220, 830),             # left hem
        (210, 390),             # left armpit
        (110, 520),             # left cuff inner
        (40, 480),              # left sleeve wrist
        (140, 280), (260, 200), # left shoulder
    ]

    pouch_poly = [
        (280, 560), (520, 560),
        (500, 750), (300, 750)
    ]

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 3
            in_body = point_in_polygon(x, y, hoodie_poly)
            
            # Distance to floor for soft drop shadow
            dist_floor = (y - 830)
            in_shadow = (790 <= y <= 890 and 180 <= x <= 620)
            
            if in_body:
                # Vintage Washed Charcoal fleece with natural gradient & knit grain
                grain = random.randint(-4, 4)
                # Lighting: brighter at chest/shoulders, darker at hem/underarms
                light = 1.0 - (y / 1000.0) * 0.25 + (x - 400) * 0.0002
                
                # Base fabric tone (washed charcoal slate)
                r = int(min(255, max(0, (42 + grain) * light)))
                g = int(min(255, max(0, (45 + grain) * light)))
                b = int(min(255, max(0, (52 + grain) * light)))

                # Ribbed hem texture (last 60px)
                if y >= 770:
                    rib = 6 if (x % 6 < 3) else -4
                    r, g, b = min(255, r + rib), min(255, g + rib), min(255, b + rib)

                # Kangaroo pouch pocket
                if point_in_polygon(x, y, pouch_poly):
                    r = min(255, int(r * 1.08))
                    g = min(255, int(g * 1.08))
                    b = min(255, int(b * 1.08))
                    if y == 560 or y == 561: # pocket seam highlight
                        r, g, b = r + 24, g + 24, b + 28

                # Hood inner fold & collar shadow
                if 140 <= y <= 320 and 310 <= x <= 490:
                    dx = (x - 400) / 75.0
                    dy = (y - 230) / 70.0
                    if dx*dx + dy*dy <= 1.0:
                        # Deep hood interior
                        r = int(r * 0.45)
                        g = int(g * 0.45)
                        b = int(b * 0.48)
                
                # Cream drawstring cords
                if 240 <= y <= 450:
                    if abs(x - 370) < 3 or abs(x - 430) < 3:
                        cord_wave = math.sin(y * 0.05) * 4
                        if (abs(x - (370 + cord_wave)) < 3) or (abs(x - (430 - cord_wave)) < 3):
                            r, g, b = 238, 232, 218 # off-white woven cord

                pixels[idx] = r
                pixels[idx+1] = g
                pixels[idx+2] = b
            else:
                # Studio cyclorama backdrop: clean light grey with smooth vignette
                vig = 1.0 - math.sqrt(((x - 400)/400.0)**2 + ((y - 500)/500.0)**2) * 0.06
                bg = int(246 * vig)
                
                # Soft realistic contact shadow under hoodie
                if in_shadow:
                    sh_y = (y - 830) / 60.0
                    sh_x = (x - 400) / 220.0
                    alpha = max(0.0, 1.0 - (sh_x*sh_x + sh_y*sh_y)) * 0.35
                    bg = int(bg * (1.0 - alpha) + 160 * alpha)
                
                pixels[idx] = bg
                pixels[idx+1] = bg
                pixels[idx+2] = bg + 2

    save_png_rgb("sample_hoodie.png", w, h, pixels)

# -------------------------------------------------------------
# 2. Gold Bullion Embroidery Crest Patch
# -------------------------------------------------------------
def make_embroidery_crest():
    w, h = 800, 800
    pixels = bytearray(w * h * 3)
    cx, cy, r_patch = 400, 400, 260
    random.seed(101)

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 3
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)

            if dist <= r_patch:
                angle = math.atan2(dy, dx)
                
                if dist >= r_patch - 24:
                    # Thick Merrowed Border (Dense satin stitch simulation)
                    thread_step = int(angle * 120) % 2
                    luster = 1.0 + 0.35 * math.cos(angle - 0.78) # 45-degree studio keylight
                    if thread_step == 0:
                        r, g, b = int(245 * luster), int(195 * luster), int(35 * luster)
                    else:
                        r, g, b = int(210 * luster), int(160 * luster), int(25 * luster)
                elif dist >= r_patch - 32:
                    # Inset groove shadow
                    r, g, b = 70, 50, 15
                else:
                    # Heavy Midnight Navy Twill ground with twill rib texture
                    twill = ((x + 2*y) % 6 < 3)
                    t_val = 32 if twill else 22
                    r, g, b = t_val - 2, t_val, t_val + 14
                    
                    # Central embroidered gold shield & star
                    if dist <= 140:
                        # Golden star
                        star_ang = (angle + math.pi/2) % (2*math.pi / 5) - (math.pi / 5)
                        r_star = 120.0 * math.cos(math.pi / 5) / math.cos(abs(star_ang))
                        if dist <= r_star * 0.85:
                            # Satin gold embroidery sheen
                            sheen = 0.8 + 0.4 * abs(math.cos(angle * 2.5))
                            r = int(min(255, 235 * sheen))
                            g = int(min(255, 185 * sheen))
                            b = int(min(255, 45 * sheen))
                            
                            # Center crimson ruby gem
                            if dist <= 35:
                                r, g, b = 215, 30, 45
            else:
                # Neutral studio photo ground with soft contact shadow
                bg = 244
                if r_patch < dist <= r_patch + 40:
                    falloff = 1.0 - (dist - r_patch) / 40.0
                    bg = int(bg * (1.0 - falloff * 0.28) + 160 * (falloff * 0.28))
                pixels[idx] = bg
                pixels[idx+1] = bg
                pixels[idx+2] = bg + 1
                continue

            pixels[idx] = min(255, max(0, r))
            pixels[idx+1] = min(255, max(0, g))
            pixels[idx+2] = min(255, max(0, b))

    save_png_rgb("sample_embroidery_crest.png", w, h, pixels)

# -------------------------------------------------------------
# 3. Technical Athletic Sneaker
# -------------------------------------------------------------
def make_sneaker():
    w, h = 900, 600
    pixels = bytearray(w * h * 3)
    random.seed(88)

    sole_poly = [
        (120, 440), (220, 445), (460, 445), (700, 435), (810, 390),
        (790, 345), (710, 360), (460, 370), (220, 370), (110, 400)
    ]
    upper_poly = [
        (110, 400), (220, 370), (320, 290), (480, 220), (550, 220),
        (600, 270), (710, 360), (790, 345), (750, 300), (620, 180),
        (490, 155), (370, 190), (270, 260), (160, 340), (110, 400)
    ]

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 3
            in_sole = point_in_polygon(x, y, sole_poly)
            in_upper = point_in_polygon(x, y, upper_poly)

            if in_sole:
                # White sculpted EVA midsole with horizontal cushioning grooves
                groove = 14 if (y % 16 < 4) else 0
                val = max(0, min(255, 245 - groove + (x % 5)))
                pixels[idx] = val
                pixels[idx+1] = val
                pixels[idx+2] = val
            elif in_upper:
                # Electric Cyan Knit Mesh Upper with breathable mesh texture
                mesh = 12 if ((x + y) % 6 < 3) else -8
                # Coral speed swoop overlay
                swoop = (280 <= x <= 580 and 220 <= y <= 320)
                if swoop and abs((x - 280)*0.32 - (y - 220)) < 22:
                    pixels[idx] = min(255, 248 + mesh) # Vivid Coral
                    pixels[idx+1] = max(0, 65 + mesh)
                    pixels[idx+2] = max(0, 95 + mesh)
                else:
                    pixels[idx] = max(0, 12 + mesh)    # High-voltage Cyan
                    pixels[idx+1] = min(255, 168 + mesh)
                    pixels[idx+2] = min(255, 232 + mesh)
            else:
                # Studio backdrop with horizontal ground reflection
                bg = 247 if y < 445 else 238
                # Contact shadow under sole
                if 440 <= y <= 485 and 120 <= x <= 780:
                    sy = (y - 440) / 45.0
                    bg = int(bg * (0.65 + 0.35 * sy))
                pixels[idx] = bg
                pixels[idx+1] = bg
                pixels[idx+2] = bg + 1

    save_png_rgb("sample_sneaker.png", w, h, pixels)

# -------------------------------------------------------------
# 4. Intricate Floral Lace Trim (with real negative cutaways)
# -------------------------------------------------------------
def make_lace_trim():
    w, h = 800, 600
    pixels = bytearray(w * h * 3)

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 3
            
            # Repetitive ornate Guipure lace medallions
            cell_x = x % 160 - 80
            cell_y = y % 160 - 80
            d = math.sqrt(cell_x*cell_x + cell_y*cell_y)
            ang = math.atan2(cell_y, cell_x)
            
            # 8-petal rosette formula
            petals = 45.0 + 20.0 * math.cos(ang * 8)
            in_petal_ring = abs(d - petals) < 10.0
            in_center_core = d < 18.0
            in_bridge = (abs(cell_x) < 5.0 or abs(cell_y) < 5.0) and d < 75.0
            
            # Bounding banner area (lace band)
            in_lace_band = (100 <= y <= 500 and 60 <= x <= 740)
            
            if in_lace_band and (in_petal_ring or in_center_core or in_bridge):
                # Champagne Silk embroidery thread sheen
                luster = 1.0 + 0.3 * math.cos(ang * 4 - 0.5)
                pixels[idx] = int(min(255, 252 * luster))
                pixels[idx+1] = int(min(255, 240 * luster))
                pixels[idx+2] = int(min(255, 215 * luster))
            else:
                # Studio warm cyclorama
                bg = 245 if ((x//30 + y//30)%2 == 0) else 243
                pixels[idx] = bg
                pixels[idx+1] = bg - 1
                pixels[idx+2] = bg - 3

    save_png_rgb("sample_lace_trim.png", w, h, pixels)

if __name__ == "__main__":
    make_hoodie()
    make_embroidery_crest()
    make_sneaker()
    make_lace_trim()

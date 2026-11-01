# PhotoCraft × Browzwear VStitcher — Background Removal & Artwork Placement

> High-speed, non-neural background removal engine (pure Rust) and interactive localhost inspection studio with Browzwear VStitcher Open Platform 3D garment artwork placement.

---

## ⚡ Highlights

- **Pure Rust Headless CLI Engine:** Non-neural classical segmentation pipeline (`photocraft-cli run ... --cmd layer.removeBackground`). Zero PyTorch/ONNX runtime overhead, $<150\text{ms}$ execution latency.
- **Dual-Engine Detection:**
  - **Mode 1 (`Single Subject`):** Classical GrabCut with SLIC superpixels, boundary connectivity saliency, and He et al. Guided Image Filter edge matting for apparel packshots (hoodies, sneakers, tees).
  - **Mode 2 (`Artwork Sheet / Gang Sheet`):** Adaptive perimeter cyclorama profiler designed for multi-logo grids (e.g. 10 chameleon logos), retaining 100% of fine wireframe line-art, low-contrast marks, and disconnected elements without clipping.
- **Decal Piece Isolator:** Automatic bounding-box cluster detection dividing gang sheets into individual decals (`01` through `10`) with targeted VStitcher placement code.
- **Localhost Testing Studio (`:8095`):** Subpixel curtain comparison, 4-tier fringe backdrop test (Dark Grid, Light Grid, Pitch Black, Fabric Heather Grey), zoom loupe ($1\times, 2\times, 4\times$), and real-time VStitcher script generator.
- **Browzwear VStitcher Open Platform Bridge:** Standalone Python script (`vstitcher_bg_remover.py`) invoking the CLI and placing artwork directly onto 3D garment pattern pieces (`Front_Body`, `Left_Chest`, etc.).

---

## 🏛️ Architecture

```mermaid
flowchart TD
    A["Raw Apparel / Artwork Photo\n(JPG, PNG, WebP, PSD)"] --> B{"Detection Mode Selector"}
    
    subgraph Engine ["PhotoCraft Engine (Pure Rust)"]
        B -->|Single Garment| C["SLIC Superpixels & Saliency"]
        C --> D["Boykov-Kolmogorov GrabCut (5-GMM)"]
        D --> E["He et al. Guided Filter Edge Matting"]
        E --> F["32-Bit RGBA Cutout PNG"]
    end

    subgraph SheetEngine ["Adaptive Sheet Extractor"]
        B -->|Artwork Sheet / Decal Grid| G["Perimeter Backdrop Profiler"]
        G --> H["Color Distance & Cosine Anti-Aliasing"]
        H --> I["Decal Cluster Bounding Box Detector"]
        I --> J["100% Intact Sheet Cutout\n+ Isolated Decals 01..10"]
    end

    F --> K["Localhost Review Studio\n(http://127.0.0.1:8095)"]
    J --> K

    K --> L["Interactive Curtain & Decal Selector"]
    L --> M["Browzwear VStitcher Plugin\n(vstitcher_bg_remover.py)"]
    M --> N["3D Garment Simulation\n(piece.add_artwork)"]
```

---

## 📂 Repository Structure

```
.
├── engine/                   # Pure Rust PhotoCraft engine source
│   ├── apps/photocraft-cli/  # Headless CLI runner
│   ├── crates/algo/          # GrabCut, SLIC, GMM, Guided Filter matting
│   ├── crates/engine/        # Command dispatch ("layer.removeBackground")
│   └── Cargo.toml            # Workspace manifest
├── studio/                   # Localhost interactive inspection web app
│   ├── server.py             # HTTP daemon & adaptive sheet processor (Port 8095)
│   ├── run_studio.sh         # Studio launch script
│   ├── web/index.html        # Sleek Slate studio UI with Split Curtain
│   ├── samples/              # Test fashion presets & chameleon logo sheet
│   └── output/               # Pre-computed transparent cutouts & individual decals
├── vstitcher_plugin/         # Standalone Browzwear VStitcher Python bridge
│   └── vstitcher_bg_remover.py
└── README.md
```

---

## 🚀 Quickstart

### 1. Build the Rust CLI Engine

```bash
cd engine
cargo build --release -p photocraft-cli
```

The compiled binary will be placed at `engine/target/release/photocraft-cli`.

### 2. Run the Localhost Studio

```bash
cd studio
python3 server.py
# Or launch via script:
./run_studio.sh
```

Open `http://127.0.0.1:8095` in your browser to inspect cutouts, test backdrops, and pick individual decals.

### 3. Headless CLI Usage

**Single Garment Packshot:**
```bash
./engine/target/release/photocraft-cli run input_garment.jpg \
  --cmd "layer.removeBackground" \
  --params '{"refine": true, "sampleAllLayers": false}' \
  --out cutout.png
```

**Artwork Gang Sheet (All Logos Intact):**
```bash
python3 vstitcher_plugin/vstitcher_bg_remover.py samples/chameleon_logos.png --mode sheet -o all_logos.png
```

**Isolate Single Decal (e.g. Logo 06):**
```bash
python3 vstitcher_plugin/vstitcher_bg_remover.py samples/chameleon_logos.png --mode sheet --decal 6 --piece Left_Chest
```

---

## 🧵 Browzwear VStitcher Integration

Inside Browzwear VStitcher's Python environment:

```python
import browzwear as bw
from vstitcher_plugin.vstitcher_bg_remover import remove_background

# 1. Strip background via PhotoCraft
cutout_path = remove_background("assets/chameleon_logos.png", mode="sheet", decal_index=6)

# 2. Place onto pattern piece
garment = bw.get_active_garment()
piece = garment.get_piece("Left_Chest")
artwork = piece.add_artwork(file_path=cutout_path, x_pos=150.0, y_pos=200.0)
artwork.set_scale(1.0)
if hasattr(bw, "MaterialType"):
    artwork.set_material_type(bw.MaterialType.EMBROIDERY)
```

---

## 📜 License

- Engine: Dual-licensed under [MIT](engine/LICENSE-MIT) and [Apache 2.0](engine/LICENSE-APACHE).
- Studio & VStitcher Plugin: MIT License.

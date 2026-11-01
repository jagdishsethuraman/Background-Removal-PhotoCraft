//! photocraft-cutout: Ultra-compact, headless background removal binary.
//! Supports dual-engine extraction:
//!   - `subject`: GrabCut + GMM Saliency + Guided Filter edge matting (ideal for apparel packshots).
//!   - `sheet`: Adaptive cyclorama perimeter flood + connected-component decal extractor (for gang sheets).
//!   - `auto`: Automatically selects mode based on perimeter background uniformity.

use std::collections::VecDeque;
use std::path::PathBuf;
use std::time::Instant;

use clap::{Parser, ValueEnum};
use image::{Rgba, RgbaImage};
use photocraft_algo::matting::{self, RefineParams};
use photocraft_algo::segment::SurfaceSampler;
use photocraft_algo::segment::subject::select_subject;
use photocraft_algo::selection::{combine_region, Region, SelectionMode};
use photocraft_color::PixelFormat;
use photocraft_geom::Rect;
use photocraft_raster::Surface;
use serde::Serialize;

#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
enum ExtractionMode {
    Auto,
    Subject,
    Sheet,
}

#[derive(Parser, Debug)]
#[command(
    name = "photocraft-cutout",
    about = "Ultra-lean background removal & artwork decal extractor",
    version
)]
struct Args {
    /// Path to input image (PNG, JPEG).
    #[arg(value_name = "INPUT")]
    input: PathBuf,

    /// Output path for 32-bit RGBA PNG.
    #[arg(short, long, value_name = "OUTPUT")]
    output: Option<PathBuf>,

    /// Extraction mode: auto, subject (apparel packshot), sheet (cyclorama artwork / gang sheet).
    #[arg(short, long, value_enum, default_value = "auto")]
    mode: ExtractionMode,

    /// Color tolerance threshold for cyclorama sheet extraction (default: 22.0).
    #[arg(short, long, default_value_t = 22.0)]
    tolerance: f32,

    /// Apply Guided Filter edge matting for soft fabric / thread fringe.
    #[arg(short, long, default_value_t = true)]
    refine: bool,

    /// Decal 1-based index to isolate and crop (sheet mode).
    #[arg(long, value_name = "INDEX")]
    decal: Option<usize>,

    /// Minimum connected component pixel count for decal islands.
    #[arg(long, default_value_t = 40)]
    min_island: usize,

    /// Padding margin (px) around cropped decal.
    #[arg(long, default_value_t = 16)]
    margin: u32,

    /// Emit JSON metadata to stdout.
    #[arg(long, default_value_t = false)]
    json: bool,
}

#[derive(Serialize, Debug)]
struct DecalInfo {
    id: usize,
    bbox: [i32; 4],
    width: u32,
    height: u32,
    area_px: usize,
}

#[derive(Serialize, Debug)]
struct CutoutResult {
    input: String,
    output: String,
    mode_used: String,
    width: u32,
    height: u32,
    latency_ms: u128,
    decals_detected: usize,
    selected_decal: Option<usize>,
    decals: Vec<DecalInfo>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let t0 = Instant::now();
    let args = Args::parse();

    let img = image::open(&args.input)
        .map_err(|e| format!("Failed to read input image '{}': {e}", args.input.display()))?
        .to_rgba8();

    let (width, height) = img.dimensions();
    let w = width as i32;
    let h = height as i32;
    let canvas = Rect::new(0, 0, w, h);

    // Determine mode
    let effective_mode = match args.mode {
        ExtractionMode::Subject => ExtractionMode::Subject,
        ExtractionMode::Sheet => ExtractionMode::Sheet,
        ExtractionMode::Auto => {
            if is_uniform_perimeter(&img) {
                ExtractionMode::Sheet
            } else {
                ExtractionMode::Subject
            }
        }
    };

    let mut out_rgba = img.clone();
    let mut detected_decals = Vec::new();
    let mode_str;

    match effective_mode {
        ExtractionMode::Sheet => {
            mode_str = "sheet";
            let (alpha_mask, decals) = extract_sheet_cyclorama(&img, args.tolerance, args.min_island);
            detected_decals = decals;

            // Apply alpha mask
            for y in 0..height {
                for x in 0..width {
                    let idx = (y * width + x) as usize;
                    let a = alpha_mask[idx];
                    let px = out_rgba.get_pixel_mut(x, y);
                    px[3] = (px[3] as f32 * a / 255.0).round().clamp(0.0, 255.0) as u8;
                }
            }
        }
        ExtractionMode::Subject | ExtractionMode::Auto => {
            mode_str = "subject";
            // Build PhotoCraft surface
            let mut surface = Surface::new(PixelFormat::RGBA8);
            surface.write_interleaved(canvas, img.as_raw());
            let sampler = SurfaceSampler(&surface);

            if let Some(region) = select_subject(&sampler, canvas) {
                let mask: Vec<u8> = if args.refine {
                    // Refine edge using Guided Filter
                    let sel = combine_region(None, Some(&region), SelectionMode::Replace);
                    if let Some(sel) = sel {
                        let content = sel.content_bounds();
                        let params = RefineParams {
                            radius: 8.0,
                            smooth: 2.0,
                            feather: 0.5,
                            contrast: 5.0,
                            ..Default::default()
                        };
                        if let Some(refined) = matting::refine_mask(&sampler, &matting::surface_reader(&sel), content, canvas, &params) {
                            region_to_mask(&refined, w, h)
                        } else {
                            region_to_mask(&region, w, h)
                        }
                    } else {
                        region_to_mask(&region, w, h)
                    }
                } else {
                    region_to_mask(&region, w, h)
                };

                for y in 0..height {
                    for x in 0..width {
                        let idx = (y * width + x) as usize;
                        let a = mask.get(idx).copied().unwrap_or(0);
                        let px = out_rgba.get_pixel_mut(x, y);
                        px[3] = (px[3] as f32 * a as f32 / 255.0).round().clamp(0.0, 255.0) as u8;
                    }
                }
            } else {
                // Fallback to sheet mode if subject saliency produced empty region
                let (alpha_mask, decals) = extract_sheet_cyclorama(&img, args.tolerance, args.min_island);
                detected_decals = decals;
                for y in 0..height {
                    for x in 0..width {
                        let idx = (y * width + x) as usize;
                        let a = alpha_mask[idx];
                        let px = out_rgba.get_pixel_mut(x, y);
                        px[3] = (px[3] as f32 * a / 255.0).round().clamp(0.0, 255.0) as u8;
                    }
                }
            }
        }
    }

    // Handle decal cropping if requested
    let final_img = if let Some(decal_id) = args.decal {
        if let Some(target) = detected_decals.iter().find(|d| d.id == decal_id) {
            let m = args.margin as i32;
            let bx0 = (target.bbox[0] - m).max(0) as u32;
            let by0 = (target.bbox[1] - m).max(0) as u32;
            let bx1 = (target.bbox[2] + m).min(w) as u32;
            let by1 = (target.bbox[3] + m).min(h) as u32;
            let crop_w = (bx1 - bx0).max(1);
            let crop_h = (by1 - by0).max(1);

            let mut cropped = RgbaImage::new(crop_w, crop_h);
            for cy in 0..crop_h {
                for cx in 0..crop_w {
                    let src_px = out_rgba.get_pixel(bx0 + cx, by0 + cy);
                    cropped.put_pixel(cx, cy, *src_px);
                }
            }
            cropped
        } else {
            out_rgba
        }
    } else {
        out_rgba
    };

    // Output destination
    let out_path = args.output.unwrap_or_else(|| {
        let stem = args.input.file_stem().and_then(|s| s.to_str()).unwrap_or("cutout");
        let parent = args.input.parent().unwrap_or_else(|| std::path::Path::new("."));
        parent.join(format!("{stem}_cutout.png"))
    });

    final_img.save(&out_path)
        .map_err(|e| format!("Failed to save output to '{}': {e}", out_path.display()))?;

    let elapsed = t0.elapsed().as_millis();

    if args.json {
        let summary = CutoutResult {
            input: args.input.to_string_lossy().to_string(),
            output: out_path.to_string_lossy().to_string(),
            mode_used: mode_str.to_string(),
            width: final_img.width(),
            height: final_img.height(),
            latency_ms: elapsed,
            decals_detected: detected_decals.len(),
            selected_decal: args.decal,
            decals: detected_decals,
        };
        println!("{}", serde_json::to_string_pretty(&summary)?);
    } else {
        eprintln!(
            "photocraft-cutout: done in {elapsed}ms [mode: {mode_str}, decals: {}, output: {}]",
            detected_decals.len(),
            out_path.display()
        );
    }

    Ok(())
}

fn region_to_mask(r: &Region, w: i32, h: i32) -> Vec<u8> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        for x in 0..w {
            out.push((r.at(x, y) * 255.0).round().clamp(0.0, 255.0) as u8);
        }
    }
    out
}

/// Checks whether perimeter border pixels have low standard deviation (cyclorama backdrop).
fn is_uniform_perimeter(img: &RgbaImage) -> bool {
    let (w, h) = img.dimensions();
    if w < 10 || h < 10 {
        return false;
    }
    let mut samples = Vec::with_capacity((w * 2 + h * 2) as usize);
    for x in 0..w {
        samples.push(img.get_pixel(x, 0));
        samples.push(img.get_pixel(x, h - 1));
    }
    for y in 0..h {
        samples.push(img.get_pixel(0, y));
        samples.push(img.get_pixel(w - 1, y));
    }
    let n = samples.len() as f32;
    let (mut sum_r, mut sum_g, mut sum_b) = (0.0f32, 0.0f32, 0.0f32);
    for p in &samples {
        sum_r += p[0] as f32;
        sum_g += p[1] as f32;
        sum_b += p[2] as f32;
    }
    let (mean_r, mean_g, mean_b) = (sum_r / n, sum_g / n, sum_b / n);

    let mut var = 0.0f32;
    for p in &samples {
        let dr = p[0] as f32 - mean_r;
        let dg = p[1] as f32 - mean_g;
        let db = p[2] as f32 - mean_b;
        var += dr * dr + dg * dg + db * db;
    }
    let std_dev = (var / n).sqrt();
    std_dev < 18.0
}

/// Extracts sheet cyclorama background and detects all individual decal islands.
fn extract_sheet_cyclorama(img: &RgbaImage, tolerance: f32, min_island: usize) -> (Vec<f32>, Vec<DecalInfo>) {
    let (w, h) = img.dimensions();
    let total = (w * h) as usize;
    let mut alpha = vec![255.0f32; total];
    let mut visited = vec![false; total];

    // Compute robust background color from perimeter 4 corners & edges
    let corner_samples = [
        img.get_pixel(0, 0),
        img.get_pixel(w - 1, 0),
        img.get_pixel(0, h - 1),
        img.get_pixel(w - 1, h - 1),
        img.get_pixel(w / 2, 0),
        img.get_pixel(w / 2, h - 1),
        img.get_pixel(0, h / 2),
        img.get_pixel(w - 1, h / 2),
    ];
    let mut bg_r = 0.0f32;
    let mut bg_g = 0.0f32;
    let mut bg_b = 0.0f32;
    for p in corner_samples {
        bg_r += p[0] as f32;
        bg_g += p[1] as f32;
        bg_b += p[2] as f32;
    }
    let count = corner_samples.len() as f32;
    let bg_color = [bg_r / count, bg_g / count, bg_b / count];

    let color_dist = |p: &Rgba<u8>| -> f32 {
        let dr = p[0] as f32 - bg_color[0];
        let dg = p[1] as f32 - bg_color[1];
        let db = p[2] as f32 - bg_color[2];
        (dr * dr + dg * dg + db * db).sqrt()
    };

    // Breadth-first flood fill from border pixels
    let mut queue = VecDeque::new();

    for x in 0..w {
        queue.push_back((x, 0));
        queue.push_back((x, h - 1));
    }
    for y in 0..h {
        queue.push_back((0, y));
        queue.push_back((w - 1, y));
    }

    let feather = 6.0f32;
    let tol_low = (tolerance - feather).max(0.0);
    let tol_high = tolerance + feather;

    while let Some((x, y)) = queue.pop_front() {
        let idx = (y * w + x) as usize;
        if visited[idx] {
            continue;
        }
        visited[idx] = true;

        let px = img.get_pixel(x, y);
        let dist = color_dist(px);

        if dist <= tolerance {
            alpha[idx] = 0.0;
            // Expand 4-connectivity
            if x > 0 && !visited[idx - 1] {
                queue.push_back((x - 1, y));
            }
            if x + 1 < w && !visited[idx + 1] {
                queue.push_back((x + 1, y));
            }
            if y > 0 && !visited[idx - w as usize] {
                queue.push_back((x, y - 1));
            }
            if y + 1 < h && !visited[idx + w as usize] {
                queue.push_back((x, y + 1));
            }
        } else if dist < tol_high {
            // Anti-aliased boundary ramp
            let t = ((dist - tol_low) / (tol_high - tol_low)).clamp(0.0, 1.0);
            alpha[idx] = t * 255.0;
        }
    }

    // Connected Component Analysis on foreground (alpha > 32.0)
    let mut component_labels = vec![0usize; total];
    let mut current_label = 0usize;
    let mut raw_components: Vec<(usize, i32, i32, i32, i32, usize)> = Vec::new(); // (id, x0, y0, x1, y1, area)

    for y in 0..h {
        for x in 0..w {
            let idx = (y * w + x) as usize;
            if alpha[idx] > 32.0 && component_labels[idx] == 0 {
                current_label += 1;
                let mut c_queue = VecDeque::new();
                c_queue.push_back((x, y));
                component_labels[idx] = current_label;

                let (mut min_x, mut min_y, mut max_x, mut max_y, mut area) = (x as i32, y as i32, x as i32, y as i32, 0usize);

                while let Some((cx, cy)) = c_queue.pop_front() {
                    area += 1;
                    min_x = min_x.min(cx as i32);
                    min_y = min_y.min(cy as i32);
                    max_x = max_x.max(cx as i32);
                    max_y = max_y.max(cy as i32);

                    let neighbors = [
                        (cx.wrapping_sub(1), cy),
                        (cx + 1, cy),
                        (cx, cy.wrapping_sub(1)),
                        (cx, cy + 1),
                    ];
                    for (nx, ny) in neighbors {
                        if nx < w && ny < h {
                            let n_idx = (ny * w + nx) as usize;
                            if alpha[n_idx] > 32.0 && component_labels[n_idx] == 0 {
                                component_labels[n_idx] = current_label;
                                c_queue.push_back((nx, ny));
                            }
                        }
                    }
                }

                if area >= min_island {
                    raw_components.push((current_label, min_x, min_y, max_x + 1, max_y + 1, area));
                }
            }
        }
    }

    // Filter out structural grid lines (spans > 60% of both dimensions)
    let mut filtered_components: Vec<(usize, i32, i32, i32, i32, usize)> = raw_components
        .into_iter()
        .filter(|(_lbl, x0, y0, x1, y1, area)| {
            let bw = (*x1 - *x0) as f32;
            let bh = (*y1 - *y0) as f32;
            let is_grid_line = bw > w as f32 * 0.6 && bh > h as f32 * 0.5;
            *area >= min_island && !is_grid_line
        })
        .collect();

    // If there are large artwork components (area >= 1500), focus decal indexing on those primary artworks
    let max_area = filtered_components.iter().map(|c| c.5).max().unwrap_or(0);
    if max_area > 3000 {
        let significant: Vec<_> = filtered_components.iter().cloned().filter(|c| c.5 >= 1500).collect();
        if significant.len() >= 2 {
            filtered_components = significant;
        }
    }

    // Sort detected components in natural visual reading order (top-to-bottom, left-to-right)
    // Cluster into rows by vertical center within 15% image height
    let row_threshold = (h as f32 * 0.15).max(30.0) as i32;
    filtered_components.sort_by(|a, b| {
        let cy_a = (a.2 + a.4) / 2;
        let cy_b = (b.2 + b.4) / 2;
        if (cy_a - cy_b).abs() <= row_threshold {
            let cx_a = (a.1 + a.3) / 2;
            let cx_b = (b.1 + b.3) / 2;
            cx_a.cmp(&cx_b)
        } else {
            cy_a.cmp(&cy_b)
        }
    });

    let decals = filtered_components
        .into_iter()
        .enumerate()
        .map(|(i, (_lbl, x0, y0, x1, y1, area))| DecalInfo {
            id: i + 1,
            bbox: [x0, y0, x1, y1],
            width: (x1 - x0) as u32,
            height: (y1 - y0) as u32,
            area_px: area,
        })
        .collect();

    (alpha, decals)
}

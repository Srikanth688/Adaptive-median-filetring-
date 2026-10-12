"""Adaptive Median Filtering DIP demo - Flask backend."""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
# SciPy and scikit-image are imported lazily so the Flask website can start even if
# scientific-library imports take a while or the optional SSIM dependency fails.

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads" / "original"
NOISY_DIR = BASE_DIR / "uploads" / "noisy"
RESULT_DIR = BASE_DIR / "static" / "results"
for directory in (UPLOAD_DIR, NOISY_DIR, RESULT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 800
TOKEN_RE = re.compile(r"^[a-f0-9]{16}$")
FILE_RE = re.compile(r"^[a-f0-9]{16}_(original|noisy|standard|adaptive)\.png$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["JSON_SORT_KEYS"] = False


def error(message: str, status: int = 400):
    return jsonify(ok=False, error=message), status


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_rgb_image(file_storage) -> np.ndarray:
    """Read an image safely, apply EXIF orientation, and normalize it to RGB uint8."""
    with Image.open(file_storage) as opened:
        opened = ImageOps.exif_transpose(opened)
        opened.load()
        image = opened.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.uint8).copy()


def open_saved_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()


def save_image(array: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(array, dtype=np.uint8), mode="RGB").save(path, format="PNG", optimize=True)


def add_salt_pepper_noise(image: np.ndarray, density: float) -> np.ndarray:
    """Corrupt about density fraction of pixel locations, half black and half white."""
    rng = np.random.default_rng()
    noisy = image.copy()
    height, width = image.shape[:2]
    random_map = rng.random((height, width))
    pepper = random_map < density / 2.0
    salt = (random_map >= density / 2.0) & (random_map < density)
    noisy[pepper] = 0
    noisy[salt] = 255
    return noisy


def standard_median_filter(image: np.ndarray, window_size: int = 3) -> np.ndarray:
    if window_size not in (3, 5, 7, 9):
        raise ValueError("Median window size must be 3, 5, 7, or 9.")
    output = np.empty_like(image)
    from scipy.ndimage import median_filter as scipy_median_filter
    for channel in range(3):
        output[:, :, channel] = scipy_median_filter(
            image[:, :, channel], size=window_size, mode="nearest"
        )
    return output


def adaptive_median_filter(image: np.ndarray, max_window: int = 7) -> np.ndarray:
    """Two-stage adaptive median filter, with a growing odd window per pixel/channel.

    Stage A accepts a local median only when min < median < max. Stage B keeps
    the center when min < center < max; otherwise it replaces the center with
    the median. Unresolved pixels grow through 3, 5, ... max_window.
    """
    if max_window not in (3, 5, 7, 9):
        raise ValueError("Maximum adaptive window must be 3, 5, 7, or 9.")

    from scipy.ndimage import maximum_filter, median_filter as scipy_median_filter, minimum_filter
    output = np.empty_like(image)
    for channel in range(3):
        source = image[:, :, channel]
        restored = source.copy()
        unresolved = np.ones(source.shape, dtype=bool)
        for size in range(3, max_window + 1, 2):
            local_min = minimum_filter(source, size=size, mode="nearest")
            local_max = maximum_filter(source, size=size, mode="nearest")
            local_median = scipy_median_filter(source, size=size, mode="nearest")
            stage_a = (local_median > local_min) & (local_median < local_max)
            stage_b = (source > local_min) & (source < local_max)
            accepted = unresolved & stage_a
            restored[accepted] = np.where(stage_b[accepted], source[accepted], local_median[accepted])
            unresolved[accepted] = False
            # If the largest window cannot find a valid median, use its median.
            if size == max_window:
                restored[unresolved] = local_median[unresolved]
                unresolved[unresolved] = False
        output[:, :, channel] = restored
    return output


def quality_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict:
    if reference.shape != candidate.shape:
        raise ValueError("Images must have matching dimensions to calculate metrics.")
    ref = reference.astype(np.float64)
    got = candidate.astype(np.float64)
    mse = float(np.mean((ref - got) ** 2))
    psnr = float("inf") if mse == 0 else float(20 * np.log10(255.0 / np.sqrt(mse)))
    result = {
        "mse": round(mse, 4),
        "psnr": "Infinity" if not np.isfinite(psnr) else round(psnr, 4),
        "ssim": None,
    }
    try:
        from skimage.metrics import structural_similarity
        result["ssim"] = round(float(structural_similarity(ref.astype(np.uint8), got.astype(np.uint8), channel_axis=2, data_range=255)), 5)
    except Exception:
        result["ssim"] = None
    return result


def image_path(token: str, kind: str) -> Path | None:
    if not TOKEN_RE.fullmatch(token):
        return None
    if kind == "original":
        path = UPLOAD_DIR / f"{token}_original.png"
    elif kind == "noisy":
        path = NOISY_DIR / f"{token}_noisy.png"
    elif kind in ("standard", "adaptive"):
        path = RESULT_DIR / f"{token}_{kind}.png"
    else:
        return None
    return path if path.is_file() else None


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/upload")
def upload_image():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return error("Choose an image before uploading.")
    if not allowed_file(upload.filename):
        return error("Unsupported image type. Please choose a PNG, JPG, or JPEG file.")
    try:
        clean = load_rgb_image(upload)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return error("The selected file could not be decoded as a valid image.")
    if clean.size == 0 or clean.shape[0] < 1 or clean.shape[1] < 1:
        return error("The uploaded image is empty or invalid.")

    token = uuid.uuid4().hex[:16]
    original_name = f"{token}_original.png"
    save_image(clean, UPLOAD_DIR / original_name)
    return jsonify(
        ok=True,
        image_id=token,
        original=url_for("serve_image", kind="original", filename=original_name),
        filename=Path(upload.filename).name,
        width=int(clean.shape[1]),
        height=int(clean.shape[0]),
        note=f"Image normalized to RGB and capped at {MAX_IMAGE_SIDE} px on its longest side for responsive processing.",
    )


@app.post("/add-noise")
def add_noise_route():
    payload = request.get_json(silent=True) or request.form
    token = str(payload.get("image_id", ""))
    original_file = image_path(token, "original")
    if original_file is None:
        return error("Upload an image first, then generate noise.", 404)
    try:
        density = float(payload.get("noise_density", 0.05))
        if not np.isfinite(density) or not 0.0 <= density <= 1.0:
            raise ValueError
    except (TypeError, ValueError):
        return error("Noise density must be a number between 0 and 1.")

    clean = open_saved_image(original_file)
    noisy = add_salt_pepper_noise(clean, density)
    noisy_name = f"{token}_noisy.png"
    save_image(noisy, NOISY_DIR / noisy_name)
    # A new noise realization invalidates earlier restored outputs for this token.
    for kind in ("standard", "adaptive"):
        old_result = RESULT_DIR / f"{token}_{kind}.png"
        old_result.unlink(missing_ok=True)
    return jsonify(
        ok=True,
        noisy=url_for("serve_image", kind="noisy", filename=noisy_name),
        density=density,
        metrics=quality_metrics(clean, noisy),
        message=f"Salt-and-pepper noise generated at {density:.1%} density.",
    )


@app.post("/remove-noise")
def remove_noise_route():
    payload = request.get_json(silent=True) or request.form
    token = str(payload.get("image_id", ""))
    noisy_file = image_path(token, "noisy")
    original_file = image_path(token, "original")
    if noisy_file is None or original_file is None:
        return error("Generate salt-and-pepper noise before removing it.", 409)
    filter_name = str(payload.get("filter", "adaptive")).lower()
    if filter_name not in ("standard", "adaptive"):
        return error("Choose Standard Median Filter or Adaptive Median Filter.")
    try:
        if filter_name == "standard":
            window_size = int(payload.get("window_size", 3))
            if window_size not in (3, 5, 7, 9):
                raise ValueError("Standard median window size must be 3, 5, 7, or 9.")
        else:
            window_size = int(payload.get("max_window", 7))
            if window_size not in (3, 5, 7, 9):
                raise ValueError("Adaptive maximum window must be 3, 5, 7, or 9.")
    except (TypeError, ValueError) as exc:
        return error(str(exc) or "Check the filter settings.")

    noisy = open_saved_image(noisy_file)
    clean = open_saved_image(original_file)
    started = time.perf_counter()
    if filter_name == "standard":
        restored = standard_median_filter(noisy, window_size)
        display_name = "Standard Median Filter"
        filename = f"{token}_standard.png"
    else:
        restored = adaptive_median_filter(noisy, window_size)
        display_name = "Adaptive Median Filter"
        filename = f"{token}_adaptive.png"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    output_path = RESULT_DIR / filename
    save_image(restored, output_path)
    metrics = quality_metrics(clean, restored)
    return jsonify(
        ok=True,
        filter=filter_name,
        filter_label=display_name,
        window_size=window_size,
        processing_ms=elapsed_ms,
        image=url_for("serve_image", kind=filter_name, filename=filename),
        download=url_for("download_result", filename=filename),
        metrics=metrics,
        message=f"{display_name} completed in {elapsed_ms:.2f} ms.",
    )


@app.get("/image/<kind>/<filename>")
def serve_image(kind: str, filename: str):
    if not FILE_RE.fullmatch(filename):
        return error("Invalid image filename.", 404)
    suffix_kind = filename.rsplit("_", 1)[1].removesuffix(".png")
    if kind != suffix_kind:
        return error("Image type does not match the requested file.", 404)
    if kind == "original":
        directory = UPLOAD_DIR
    elif kind == "noisy":
        directory = NOISY_DIR
    elif kind in ("standard", "adaptive"):
        directory = RESULT_DIR
    else:
        return error("Unknown image type.", 404)
    if not (directory / filename).is_file():
        return error("Image file not found.", 404)
    return send_from_directory(directory, filename, mimetype="image/png", as_attachment=False)


@app.get("/download/<filename>")
def download_result(filename: str):
    if not FILE_RE.fullmatch(filename) or not filename.endswith(("_standard.png", "_adaptive.png")):
        return error("Invalid restored-image filename.", 404)
    file_path = RESULT_DIR / filename
    if not file_path.is_file():
        return error("The restored image is no longer available. Please run the filter again.", 404)
    download_name = "adaptive_median_restored.png" if filename.endswith("_adaptive.png") else "standard_median_restored.png"
    return send_from_directory(RESULT_DIR, filename, mimetype="image/png", as_attachment=True, download_name=download_name)


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(ok=False, error="File is too large. The maximum upload size is 10 MB."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

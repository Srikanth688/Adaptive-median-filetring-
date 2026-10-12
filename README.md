<<<<<<< HEAD
# Adaptive Median Filter — Digital Image Processing Project

A lightweight image-restoration website built with HTML, CSS, vanilla JavaScript, Python, Flask, NumPy, Pillow, and SciPy. It lets you upload an image, create salt-and-pepper noise, apply a standard median filter or a two-stage adaptive median filter, compare generated results, inspect real image-quality metrics, and download a restored image.

## Features

- PNG/JPG/JPEG upload validation in browser and Flask (maximum 10 MB).
- Original, noisy, and restored images stored separately with generated filenames.
- Salt-and-pepper noise generated from the original clean image; default density 0.05 (5% of pixel locations, split between black and white).
- Standard median filter with configurable odd window size.
- Genuine two-stage adaptive median filter. It grows through 3×3, 5×5, etc. up to the selected maximum and applies Stage A/Stage B decisions per color channel.
- MSE, PSNR, and SSIM (SSIM is optional if its dependency cannot load).
- Download of the actual generated result; adaptive and standard outputs receive descriptive download names.
- Responsive, framework-free interface.

## Run on Windows

Open PowerShell in the `adaptive-median-dip` project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in your browser. Keep the terminal open while using the website. Stop the server with `Ctrl+C`.

If PowerShell blocks virtual-environment activation, you can run the venv's Python directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Workflow

1. Select a PNG or JPG/JPEG file and press **Upload image**.
2. Adjust noise density and press **Add Salt & Pepper Noise**.
3. Choose Standard Median or Adaptive Median, set an odd window size, then press **Remove Noise**.
4. Run the other filter as well to fill both restored-image comparison panels.
5. Review MSE/PSNR/SSIM against the clean original and download the last generated restored result.

## API routes

- `GET /` — website
- `POST /upload` — validate and save original upload
- `POST /add-noise` — create a noisy copy from the original
- `POST /remove-noise` — apply selected filter to the noisy image
- `GET /image/<kind>/<filename>` — safely serve a generated image
- `GET /download/<filename>` — download an actual restored result

## Image handling and metrics

Images are converted to RGB and resized proportionally so their longest side is at most 800 pixels. This keeps processing responsive and ensures every compared image has identical dimensions. The uploaded image is preserved as a separate file. Noise density is the fraction of pixel locations selected for corruption; each selected location becomes black or white with roughly equal probability.

MSE is better when lower, PSNR is generally better when higher, and SSIM is generally better closer to 1. A PSNR value of infinity indicates identical images (MSE is zero). Metrics are calculated from actual arrays, not hardcoded values.

## Project structure

```text
adaptive-median-dip/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── results/.gitkeep
└── uploads/
    ├── original/.gitkeep
    └── noisy/.gitkeep
```

Generated image files are ignored by Git. This is a local learning/demo application; for public production deployment, add authentication, cleanup policies for uploaded files, CSRF protections where relevant, and a production WSGI server.

## Run automated smoke tests

After installing `requirements.txt`, run from the project root:

```powershell
python -m unittest discover -s tests -v
```

The tests cover upload, noise generation, both filters, metrics, result-image serving, downloads, and invalid settings.
=======
# Adaptive-median-filetring-
>>>>>>> a8f42424212c7724a00ce9a4d7fb9f722ed8d2b7

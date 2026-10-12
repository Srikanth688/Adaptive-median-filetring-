"""Integration smoke tests. Run with: python -m unittest discover -s tests -v"""
from io import BytesIO
import unittest

import numpy as np
from PIL import Image

import app as dip_app


class AdaptiveMedianWorkflowTests(unittest.TestCase):
    def setUp(self):
        dip_app.app.config.update(TESTING=True)
        self.client = dip_app.app.test_client()
        self.clean = np.zeros((32, 32, 3), dtype=np.uint8)
        self.clean[:, :16] = (40, 120, 180)
        self.clean[:, 16:] = (210, 210, 210)
        self.clean[8:24, 8:24] = (255, 255, 255)
        buffer = BytesIO()
        Image.fromarray(self.clean).save(buffer, format="PNG")
        self.png_bytes = buffer.getvalue()

    def upload(self):
        response = self.client.post(
            "/upload",
            data={"image": (BytesIO(self.png_bytes), "sample.png", "image/png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["width"], 32)
        self.assertEqual(payload["height"], 32)
        return payload

    def test_full_upload_noise_filter_and_download_flow(self):
        uploaded = self.upload()
        original_response = self.client.get(uploaded["original"])
        self.assertEqual(original_response.status_code, 200)

        noise_response = self.client.post(
            "/add-noise", json={"image_id": uploaded["image_id"], "noise_density": 0.15}
        )
        self.assertEqual(noise_response.status_code, 200, noise_response.get_data(as_text=True))
        noisy = noise_response.get_json()
        noisy_image = np.asarray(Image.open(BytesIO(self.client.get(noisy["noisy"]).data)).convert("RGB"))
        self.assertFalse(np.array_equal(noisy_image, self.clean))
        self.assertIn("mse", noisy["metrics"])
        self.assertIn("psnr", noisy["metrics"])

        for filter_name, settings in (("standard", {"window_size": 3}), ("adaptive", {"max_window": 5})):
            response = self.client.post(
                "/remove-noise", json={"image_id": uploaded["image_id"], "filter": filter_name, **settings}
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            result = response.get_json()
            self.assertGreaterEqual(result["processing_ms"], 0)
            self.assertIn("mse", result["metrics"])
            restored_response = self.client.get(result["image"])
            self.assertEqual(restored_response.status_code, 200)
            restored = Image.open(BytesIO(restored_response.data))
            self.assertEqual(restored.size, (32, 32))
            download_response = self.client.get(result["download"])
            self.assertEqual(download_response.status_code, 200)
            self.assertIn("attachment", download_response.headers.get("Content-Disposition", ""))

    def test_invalid_file_type_and_invalid_settings(self):
        response = self.client.post(
            "/upload", data={"image": (BytesIO(b"not an image"), "notes.txt")}, content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 400)

        uploaded = self.upload()
        response = self.client.post(
            "/add-noise", json={"image_id": uploaded["image_id"], "noise_density": 1.5}
        )
        self.assertEqual(response.status_code, 400)

        self.client.post("/add-noise", json={"image_id": uploaded["image_id"], "noise_density": 0.05})
        response = self.client.post(
            "/remove-noise", json={"image_id": uploaded["image_id"], "filter": "adaptive", "max_window": 4}
        )
        self.assertEqual(response.status_code, 400)

    def test_filter_algorithms_preserve_shape_and_type(self):
        noisy = dip_app.add_salt_pepper_noise(self.clean, 0.2)
        self.assertEqual(noisy.shape, self.clean.shape)
        self.assertEqual(noisy.dtype, np.uint8)
        standard = dip_app.standard_median_filter(noisy, 3)
        adaptive = dip_app.adaptive_median_filter(noisy, 5)
        self.assertEqual(standard.shape, self.clean.shape)
        self.assertEqual(adaptive.shape, self.clean.shape)
        self.assertEqual(standard.dtype, np.uint8)
        self.assertEqual(adaptive.dtype, np.uint8)
        self.assertIn("mse", dip_app.quality_metrics(self.clean, adaptive))


if __name__ == "__main__":
    unittest.main()

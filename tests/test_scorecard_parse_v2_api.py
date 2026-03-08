"""Tests for the /api/scorecard/parse_v2 endpoint contract."""
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


class TestParseV2Endpoint(unittest.TestCase):

    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    @patch("app.main.extract_word_boxes")
    @patch("app.main.get_image_date")
    def test_returns_draft_round_shape(
        self, mock_date: object, mock_ocr: object,
    ) -> None:
        """Mocked OCR returning synthetic word boxes produces a DraftRound."""
        from app.vision_ocr import WordBox

        mock_date.return_value = None  # type: ignore[attr-defined]
        mock_ocr.return_value = (  # type: ignore[attr-defined]
            "Hole 1 2 3 Total\nPar 4 5 3 12\nAlice 4 5 3 12\nBob 5 6 4 15",
            [
                WordBox("Hole", 40, 20, 14, 26),
                WordBox("1", 120, 20, 14, 26),
                WordBox("2", 200, 20, 14, 26),
                WordBox("3", 280, 20, 14, 26),
                WordBox("Total", 380, 20, 14, 26),
                WordBox("Par", 40, 50, 44, 56),
                WordBox("4", 120, 50, 44, 56),
                WordBox("5", 200, 50, 44, 56),
                WordBox("3", 280, 50, 44, 56),
                WordBox("12", 380, 50, 44, 56),
                WordBox("Alice", 40, 80, 74, 86),
                WordBox("4", 120, 80, 74, 86),
                WordBox("5", 200, 80, 74, 86),
                WordBox("3", 280, 80, 74, 86),
                WordBox("12", 380, 80, 74, 86),
                WordBox("Bob", 40, 110, 104, 116),
                WordBox("5", 120, 110, 104, 116),
                WordBox("6", 200, 110, 104, 116),
                WordBox("4", 280, 110, 104, 116),
                WordBox("15", 380, 110, 104, 116),
            ],
        )

        # Create a minimal JPEG-ish byte stream
        import numpy as np, cv2
        img = np.ones((140, 500, 3), dtype=np.uint8) * 255
        _, buf = cv2.imencode(".jpg", img)
        image_bytes = bytes(buf)

        resp = self.client.post(
            "/api/scorecard/parse_v2",
            files={"scorecard_image": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
            data={"scorecard_is_warped": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertIn("players", body)
        self.assertIn("hole_pars", body)
        self.assertIn("stroke_indexes", body)
        self.assertIn("prediction_meta", body)
        self.assertIn("scorecard_grid", body)
        self.assertIn("predicted_mapping", body)
        self.assertIn("repaired_cells", body)
        self.assertIsInstance(body["players"], list)
        self.assertEqual(len(body["hole_pars"]), 18)

    @patch("app.main.extract_word_boxes")
    @patch("app.main.get_image_date")
    def test_debug_flag_includes_debug_layout(
        self, mock_date: object, mock_ocr: object,
    ) -> None:
        from app.vision_ocr import WordBox

        mock_date.return_value = None  # type: ignore[attr-defined]
        mock_ocr.return_value = (  # type: ignore[attr-defined]
            "Hole 1 2 3\nAlice 4 5 3",
            [
                WordBox("Hole", 40, 20, 14, 26),
                WordBox("1", 120, 20, 14, 26),
                WordBox("2", 200, 20, 14, 26),
                WordBox("3", 280, 20, 14, 26),
                WordBox("Alice", 40, 50, 44, 56),
                WordBox("4", 120, 50, 44, 56),
                WordBox("5", 200, 50, 44, 56),
                WordBox("3", 280, 50, 44, 56),
            ],
        )

        import numpy as np, cv2
        img = np.ones((80, 400, 3), dtype=np.uint8) * 255
        _, buf = cv2.imencode(".jpg", img)
        image_bytes = bytes(buf)

        resp = self.client.post(
            "/api/scorecard/parse_v2",
            files={"scorecard_image": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
            data={"scorecard_is_warped": "true", "debug": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("debug_layout", body)
        self.assertIn("strategy_used", body["debug_layout"])
        self.assertIn("n_tokens", body["debug_layout"])

    def test_no_image_returns_422(self) -> None:
        """Omitting the required scorecard_image should fail."""
        resp = self.client.post("/api/scorecard/parse_v2")
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()

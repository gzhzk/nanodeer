"""Tests for read_image tool."""
import pytest
from pathlib import Path

from nanodeer.tools.read_image import read_image


class TestReadImageTool:
    def test_invoke_nonexistent_file(self):
        """Nonexistent file returns error."""
        result = read_image.invoke({"image_path": "/nonexistent/image.png"})
        assert "Error" in result
        assert "not found" in result

    def test_invoke_unsupported_format(self, tmp_path):
        """Unsupported format returns error."""
        fake = tmp_path / "document.pdf"
        fake.write_bytes(b"PDF content")
        result = read_image.invoke({"image_path": str(fake)})
        assert "Error" in result
        assert "unsupported" in result.lower()

    def test_invoke_file_too_large(self, tmp_path):
        """File over 10MB returns error."""
        large = tmp_path / "large.png"
        # Write 11MB of data
        large.write_bytes(b"x" * (11 * 1024 * 1024))
        result = read_image.invoke({"image_path": str(large)})
        assert "Error" in result
        assert "too large" in result

    def test_invoke_valid_image(self, tmp_path):
        """Valid image returns base64 data."""
        img = tmp_path / "test.png"
        # Create a minimal valid PNG (1x1 transparent pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
            b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img.write_bytes(png_data)

        result = read_image.invoke({
            "image_path": str(img),
            "description_request": "What is this image?"
        })

        assert "[IMAGE_DATA_START]" in result
        assert "[IMAGE_DATA_END]" in result
        assert "[REQUEST:]" in result
        assert "[SIZE:]" in result
        assert "[FORMAT:] png" in result

    def test_invoke_description_included(self, tmp_path):
        """Custom description is included in result."""
        img = tmp_path / "test.png"
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
            b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img.write_bytes(png_data)

        result = read_image.invoke({
            "image_path": str(img),
            "description_request": "Extract all text from this image"
        })

        assert "Extract all text from this image" in result

    def test_invoke_webp_format(self, tmp_path):
        """WEBP format is supported."""
        img = tmp_path / "test.webp"
        # Create minimal WEBP
        webp_data = b"RIFF\x00\x00\x00\x00WEBPVP8 \x00\x00\x00\x00\x00\x00"
        img.write_bytes(webp_data)

        result = read_image.invoke({"image_path": str(img)})
        assert "[FORMAT:] webp" in result

    def test_invoke_gif_format(self, tmp_path):
        """GIF format is supported."""
        img = tmp_path / "test.gif"
        # Create minimal GIF
        gif_data = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;\x00\x00\x00\x00"
        img.write_bytes(gif_data)

        result = read_image.invoke({"image_path": str(img)})
        assert "[FORMAT:] gif" in result

    def test_invoke_bmp_format(self, tmp_path):
        """BMP format is supported."""
        img = tmp_path / "test.bmp"
        # Create minimal BMP
        bmp_data = b"BM\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        img.write_bytes(bmp_data)

        result = read_image.invoke({"image_path": str(img)})
        assert "[FORMAT:] bmp" in result

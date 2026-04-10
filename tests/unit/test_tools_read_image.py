"""Unit tests for read_image tool."""
import pytest

from nanodeer.tools.read_image import read_image


class TestReadImage:
    """Test read_image tool."""

    def test_returns_string(self):
        """read_image returns string."""
        result = read_image.invoke({"image_path": "/nonexistent/image.png"})
        assert isinstance(result, str)

    def test_error_nonexistent_file(self):
        """Returns error for nonexistent file."""
        result = read_image.invoke({"image_path": "/nonexistent/image.png"})
        assert "Error" in result or "not found" in result.lower()

    def test_empty_path(self):
        """Returns error for empty path."""
        result = read_image.invoke({"image_path": ""})
        assert "Error" in result or "required" in result.lower()

    def test_description_parameter(self):
        """Accepts description_request parameter."""
        result = read_image.invoke({
            "image_path": "/nonexistent.png",
            "description_request": "What is this?"
        })
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

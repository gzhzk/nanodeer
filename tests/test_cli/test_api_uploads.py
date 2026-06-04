from nanodeer.cli.api import _parse_uploaded_files


def test_parse_uploaded_files_decodes_base64_and_sanitizes_name():
    files, error = _parse_uploaded_files([
        {
            "name": "../screen.png",
            "content": "aGVsbG8=",
            "mime_type": "image/png",
            "encoding": "base64",
        }
    ])

    assert error is None
    assert files == [
        {
            "name": "screen.png",
            "content": b"hello",
            "mime_type": "image/png",
        }
    ]


def test_parse_uploaded_files_rejects_invalid_base64():
    files, error = _parse_uploaded_files([
        {
            "name": "screen.png",
            "content": "not base64!",
            "mime_type": "image/png",
            "encoding": "base64",
        }
    ])

    assert files == []
    assert error == "uploaded_files[0] has invalid base64 content"

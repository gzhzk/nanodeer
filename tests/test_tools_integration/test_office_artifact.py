import zipfile

import pytest

from nanodeer.tools.office_artifact import office_artifact
from nanodeer.workspace import Workspace, bind_workspace


@pytest.fixture
def workspace(tmp_path):
    return Workspace("office-test", tmp_path / "user-data").ensure()


@pytest.mark.parametrize(
    ("file_name", "arguments", "expected_parts", "expected_text"),
    [
        (
            "brief.docx",
            {"title": "Quarterly Brief", "content": "Revenue increased\nRisks remain"},
            {"word/document.xml"},
            "Revenue increased",
        ),
        (
            "sales.xlsx",
            {"title": "Sales", "data": [["Region", "Revenue"], ["East", 120]]},
            {"xl/workbook.xml", "xl/worksheets/sheet1.xml"},
            "East\t120",
        ),
        (
            "review.pptx",
            {"title": "Review", "slides": [{"title": "Status", "body": "On track"}]},
            {"ppt/presentation.xml", "ppt/slides/slide1.xml"},
            "On track",
        ),
    ],
)
def test_create_and_inspect_office_artifacts(
    workspace, file_name, arguments, expected_parts, expected_text
):
    virtual_path = f"/outputs/{file_name}"
    with bind_workspace(workspace):
        result = office_artifact.invoke({
            "action": "create",
            "file_path": virtual_path,
            **arguments,
        })
        inspected = office_artifact.invoke({"action": "inspect", "file_path": virtual_path})

    assert result.startswith("Created ")
    assert expected_text in inspected
    physical = workspace.outputs / file_name
    with zipfile.ZipFile(physical) as archive:
        assert archive.testzip() is None
        assert expected_parts <= set(archive.namelist())


def test_spreadsheet_requires_data(workspace):
    with bind_workspace(workspace):
        result = office_artifact.invoke({
            "action": "create",
            "file_path": "/outputs/empty.xlsx",
        })
    assert result == "Error: spreadsheet creation requires non-empty data"


def test_office_artifact_respects_workspace_boundary(workspace):
    with bind_workspace(workspace):
        result = office_artifact.invoke({
            "action": "create",
            "file_path": "/outputs/../escape.docx",
            "content": "no",
        })
    assert result.startswith("Error handling office artifact")


def test_office_artifact_schema_is_one_compact_boundary():
    schema = office_artifact.get_input_schema().model_json_schema()
    assert {"action", "file_path", "title", "content", "data", "slides"} <= set(
        schema["properties"]
    )
    assert set(schema["required"]) == {"action", "file_path"}

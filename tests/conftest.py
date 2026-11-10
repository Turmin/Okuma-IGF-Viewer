import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def source_folders(tmp_path):
    """A small IGF backup with matching (and missing) PDFs and thumbnails."""
    igf = tmp_path / "Backup 2026-01-01"
    pdf = tmp_path / "pdf" / "code"
    thumbnails = tmp_path / "Thumbnail_3D" / "code"

    programs = {
        "AD0/AS-30": ["A16-10227615-OAL.PDA", "B20-10230001-OAL.pda", "notes.txt", "SHORT-123.PDA"],
        "AD0/AS-40": ["D0003650-OAL.PDA"],
    }
    for folder, names in programs.items():
        (igf / folder).mkdir(parents=True)
        for name in names:
            (igf / folder / name).write_text("program")

    (pdf / "1022x").mkdir(parents=True)
    (pdf / "1022x" / "10227615.pdf").write_text("pdf")
    (pdf / "1022x" / "readme.pdf").write_text("pdf")
    (thumbnails / "1022x").mkdir(parents=True)
    (thumbnails / "1022x" / "10227615.JPG").write_text("jpg")
    (thumbnails / "1022x" / "0003650.jpg").write_text("jpg")
    return igf, pdf, thumbnails

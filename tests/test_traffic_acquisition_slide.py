from pathlib import Path

from pptx import Presentation

from reports.generator_2026 import (
    TEMPLATES_2026,
    _find_traffic_acquisition_slide_index,
    get_templates_dir,
)


def test_finds_traffic_acquisition_slide_in_infraco_template():
    template_path = get_templates_dir() / TEMPLATES_2026["infraco"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx == 6


def test_returns_none_when_slide_absent():
    template_path = get_templates_dir() / TEMPLATES_2026["zimplats"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx is None

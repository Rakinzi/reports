from io import BytesIO

from PIL import Image
import pytest

from reports.ga4_screenshots import capture_ga4_table


def _png(color, height):
    image = Image.new("RGB", (1523, height), color)
    data = BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


class _Locator:
    def __init__(self, *, box=None, png=None, text="", children=None):
        self.box = box
        self.png = png
        self.text = text
        self.children = children or {}
        self.first = self

    def locator(self, selector):
        return self.children[selector]

    def wait_for(self, **_):
        pass

    def bounding_box(self):
        return self.box

    def screenshot(self):
        return self.png

    def inner_text(self):
        return self.text

    def all(self):
        return self.children["items"]

    def count(self):
        return len(self.children["items"])

    def nth(self, index):
        return self.children["items"][index]


def test_captures_last_row_and_trims_empty_table_width(tmp_path):
    header = _Locator(png=_png("white", 120))
    rows = [_Locator(png=_png("gray", 41), text="Total")]
    rows += [_Locator(png=_png("blue", 41), text=f"{i} Country") for i in range(1, 11)]
    table = _Locator(
        box={"x": 0, "y": 0, "width": 1523, "height": 571},
        children={
            "thead": header,
            "thead th": _Locator(children={"items": [
                _Locator(box={"x": 700, "width": 130}, text="Engaged\nsessions per active user"),
                _Locator(box={"x": 1000, "width": 138}, text="Event count"),
                _Locator(box={"x": 1138, "width": 385}, text=""),
            ]}),
            "tbody tr": _Locator(children={"items": rows}),
        },
    )

    class Page:
        mouse = type("Mouse", (), {"move": lambda *args: None})()

        def locator(self, selector):
            assert selector == "table.adv-table"
            return table

    path = tmp_path / "table.png"
    capture_ga4_table(Page(), path)
    with Image.open(path) as image:
        assert image.size == (1146, 571)
        assert image.getpixel((500, 550)) == (0, 0, 255)

    capture_ga4_table(Page(), path, last_column="engaged sessions per active user")
    with Image.open(path) as image:
        assert image.size == (838, 571)

    capture_ga4_table(Page(), path, last_column="event count")
    with Image.open(path) as image:
        assert image.size == (1146, 571)

    with pytest.raises(RuntimeError, match="missing the 'Conversions' column"):
        capture_ga4_table(Page(), path, last_column="Conversions")

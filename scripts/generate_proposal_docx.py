from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MD = ROOT / "PROJECT_PROPOSAL.md"
BUILD_DIR = ROOT / "build" / "proposal_docx"
TEMP_MD = BUILD_DIR / "PROJECT_PROPOSAL_for_word.md"
DIAGRAM_PNG = BUILD_DIR / "architecture_overview.png"
OUTPUT_DOCX = ROOT / "PROJECT_PROPOSAL.docx"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                Path("C:/Windows/Fonts/malgunbd.ttf"),
                Path("C:/Windows/Fonts/arialbd.ttf"),
            ]
        )
    candidates.extend(
        [
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _text_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    fill: str,
    outline: str = "#3F3F46",
    text_fill: str = "#111827",
    radius: int = 24,
    font: ImageFont.ImageFont | None = None,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)
    font = font or _load_font(28)

    text_bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=6)
    tw = text_bbox[2] - text_bbox[0]
    th = text_bbox[3] - text_bbox[1]
    tx = x1 + ((x2 - x1) - tw) / 2
    ty = y1 + ((y2 - y1) - th) / 2 - 2
    draw.multiline_text((tx, ty), text, font=font, fill=text_fill, align="center", spacing=6)


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = "#374151",
    width: int = 5,
    head_len: int = 16,
    head_half: int = 9,
) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=width)

    if x1 == x2 and y1 == y2:
        return

    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        p1 = (x2, y2)
        p2 = (x2 - direction * head_len, y2 - head_half)
        p3 = (x2 - direction * head_len, y2 + head_half)
    else:
        direction = 1 if y2 > y1 else -1
        p1 = (x2, y2)
        p2 = (x2 - head_half, y2 - direction * head_len)
        p3 = (x2 + head_half, y2 - direction * head_len)
    draw.polygon([p1, p2, p3], fill=color)


def _orthogonal_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    color: str = "#374151",
    width: int = 5,
) -> None:
    for idx in range(len(points) - 2):
        _arrow(draw, points[idx], points[idx + 1], color=color, width=width, head_len=0, head_half=0)
    _arrow(draw, points[-2], points[-1], color=color, width=width)


def render_architecture_diagram(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 2000, 1200
    img = Image.new("RGB", (width, height), "#FCFCFD")
    draw = ImageDraw.Draw(img)

    title_font = _load_font(44, bold=True)
    node_font = _load_font(28)
    small_font = _load_font(24)

    draw.text((70, 40), "System Architecture Overview", font=title_font, fill="#111827")
    draw.text(
        (70, 100),
        "Proposal block diagram converted from the markdown mermaid flowchart.",
        font=small_font,
        fill="#4B5563",
    )

    boxes = {
        "user": (90, 300, 340, 420),
        "web": (430, 290, 760, 430),
        "roster": (860, 200, 1160, 320),
        "mlb": (860, 400, 1160, 520),
        "db": (1280, 290, 1560, 430),
        "sheet": (1640, 290, 1970, 430),
        "cpi": (1680, 480, 1930, 600),
        "etl": (1270, 610, 1570, 730),
        "perf": (1120, 850, 1420, 970),
        "market": (1470, 850, 1770, 970),
        "value": (1050, 1030, 1350, 1135),
        "aav": (1540, 1030, 1840, 1135),
    }

    _text_box(draw, boxes["user"], "General Manager", fill="#DBEAFE", font=node_font)
    _text_box(draw, boxes["web"], "Django Web Service", fill="#E0F2FE", font=node_font)
    _text_box(draw, boxes["roster"], "Roster App", fill="#E9D5FF", font=node_font)
    _text_box(draw, boxes["mlb"], "MLB Analysis App", fill="#F5D0FE", font=node_font)
    _text_box(draw, boxes["db"], "Service DB", fill="#DCFCE7", font=node_font)
    _text_box(draw, boxes["sheet"], "Contract / Salary\nGoogle Sheets", fill="#FDE68A", font=node_font)
    _text_box(draw, boxes["cpi"], "IMF CPI Data", fill="#FDE68A", font=node_font)
    _text_box(draw, boxes["etl"], "ETL / Feature\nEngineering", fill="#FECACA", font=node_font)
    _text_box(draw, boxes["perf"], "Performance Model", fill="#FED7AA", font=node_font)
    _text_box(draw, boxes["market"], "Market Model", fill="#FED7AA", font=node_font)
    _text_box(draw, boxes["value"], "Predicted Value", fill="#D1FAE5", font=node_font)
    _text_box(draw, boxes["aav"], "Predicted AAV", fill="#D1FAE5", font=node_font)

    _arrow(draw, (340, 360), (430, 360))
    _arrow(draw, (760, 325), (860, 260))
    _arrow(draw, (760, 395), (860, 460))
    _arrow(draw, (1160, 260), (1280, 330))
    _arrow(draw, (1160, 460), (1280, 390))

    _arrow(draw, (1160, 430), (1640, 360))
    _arrow(draw, (1160, 470), (1680, 540))

    _arrow(draw, (1420, 430), (1420, 610))
    _arrow(draw, (1420, 730), (1270, 910))
    _arrow(draw, (1520, 730), (1620, 910))
    _arrow(draw, (1270, 970), (1200, 1030))
    _arrow(draw, (1620, 970), (1690, 1030))

    _orthogonal_arrow(draw, [(1200, 1030), (1200, 770), (595, 770), (595, 430)])
    _orthogonal_arrow(draw, [(1690, 1030), (1690, 800), (650, 800), (650, 430)])

    legend_x, legend_y = 70, 1030
    draw.rounded_rectangle((legend_x, legend_y, 850, 1140), radius=18, fill="#F9FAFB", outline="#D1D5DB", width=2)
    draw.text((legend_x + 24, legend_y + 18), "Flow: data sources -> DB -> ETL -> models -> decision outputs", font=small_font, fill="#374151")
    draw.text((legend_x + 24, legend_y + 58), "Outputs are returned to the web UI for roster and contract decisions.", font=small_font, fill="#374151")

    img.save(output_path)


def prepare_markdown(source_md: Path, output_md: Path, image_name: str) -> None:
    content = source_md.read_text(encoding="utf-8")
    mermaid_pattern = re.compile(r"```mermaid\s+.*?```", re.DOTALL)

    replacement = (
        f"![시스템 아키텍처 개요]({image_name})"
        "{ width=95% }\n\n"
        "*그림 1. 제안 시스템의 상위 수준 아키텍처 구성도*"
    )
    updated, count = mermaid_pattern.subn(replacement, content, count=1)
    if count != 1:
        raise RuntimeError("Expected exactly one mermaid diagram block in PROJECT_PROPOSAL.md.")

    output_md.write_text(updated, encoding="utf-8")


def generate_docx(input_md: Path, output_docx: Path) -> None:
    cmd = [
        "pandoc",
        "--from",
        "gfm",
        "--to",
        "docx",
        "--standalone",
        "--output",
        str(output_docx),
        str(input_md),
    ]
    subprocess.run(cmd, check=True, cwd=str(input_md.parent))


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    render_architecture_diagram(DIAGRAM_PNG)
    prepare_markdown(SOURCE_MD, TEMP_MD, DIAGRAM_PNG.name)
    generate_docx(TEMP_MD, OUTPUT_DOCX)
    print(f"Generated: {OUTPUT_DOCX}")
    print(f"Diagram:   {DIAGRAM_PNG}")
    print(f"Markdown:  {TEMP_MD}")


if __name__ == "__main__":
    main()

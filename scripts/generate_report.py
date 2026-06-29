import argparse
import base64
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def encode_frame(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def build_summary(analyses: list[dict]) -> str:
    handles = sorted({a.get("handle") for a in analyses if a.get("handle")})
    formats = [a.get("visual_format") for a in analyses
               if a.get("visual_format") and a.get("analyzed")]
    top_format = Counter(formats).most_common(1)[0][0] if formats else "n/a"
    analyzed = sum(1 for a in analyses if a.get("analyzed"))
    return (
        f"Analyzed {analyzed}/{len(analyses)} top posts across "
        f"{len(handles)} handles ({', '.join(handles)}). "
        f"Most common format: {top_format}."
    )


def render_report(analyses: list[dict], summary: str, date_str: str, template_path: str) -> str:
    posts = []
    for idx, a in enumerate(analyses, start=1):
        posts.append({
            **a,
            "rank": idx,
            "thumbnail": encode_frame((a.get("frames") or [None])[0]),
        })
    env = Environment(
        loader=FileSystemLoader(os.path.dirname(template_path)),
        autoescape=True,
    )
    template = env.get_template(os.path.basename(template_path))
    handles = sorted({a.get("handle") for a in analyses if a.get("handle")})
    return template.render(
        posts=posts, summary=summary, date_str=date_str,
        handles=handles, total=len(analyses),
    )


def generate_report(input_path: str, output_dir: str, summary_path: str | None = None,
                    date_str: str | None = None, pdf: bool = False) -> str:
    with open(input_path, encoding="utf-8") as f:
        analyses = json.load(f)

    summary = build_summary(analyses)
    if summary_path and os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as f:
            summary = f.read().strip() or summary

    date_str_is_override = date_str is not None
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    html = render_report(analyses, summary, date_str,
                         str(TEMPLATE_DIR / "report.html.j2"))

    os.makedirs(output_dir, exist_ok=True)
    # Run-versioned filename: a real run (no date_str) stamps date_HHMM so same-day
    # re-runs never overwrite. An explicit date_str is used as-is (deterministic, for
    # tests / scripted calls). The header inside the report always shows date_str.
    if date_str_is_override:
        stamp = date_str
    else:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = os.path.join(output_dir, f"IG-Competitor-Research_{stamp}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote report -> {out_path}")

    if pdf:
        # Dual import: works both as a package (pytest / `python -m`) and when this
        # script is run standalone (e.g. `python …/scripts/generate_report.py`), where
        # only this file's directory is on sys.path.
        try:
            from scripts.generate_pdf import render_pdf
        except ModuleNotFoundError:
            from generate_pdf import render_pdf
        pdf_path = os.path.join(output_dir, f"IG-Competitor-Research_{stamp}.pdf")
        if render_pdf(out_path, pdf_path):
            print(f"Wrote PDF -> {pdf_path}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate HTML research report")
    parser.add_argument("--input", default="temp/analyses.json")
    parser.add_argument("--output-dir", default="output/reports")
    parser.add_argument("--summary", default="temp/niche_summary.txt")
    parser.add_argument("--pdf", action=argparse.BooleanOptionalAction, default=True,
                        help="also render a PDF from the HTML (requires Playwright)")
    args = parser.parse_args()
    generate_report(
        args.input, args.output_dir,
        summary_path=args.summary if args.summary else None,
        pdf=args.pdf,
    )

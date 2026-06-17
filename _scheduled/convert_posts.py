#!/usr/bin/env python3
"""
Wove Blog Post Converter
Converts markdown blog posts (downloaded from Google Drive) into:
  - _scheduled/manifests/YYYY-MM-DD-{slug}.json   (metadata)
  - _scheduled/bodies/YYYY-MM-DD-{slug}-body.html  (article body HTML)

Usage:
  python3 _scheduled/convert_posts.py --posts-dir ./drive-exports --schedule ./publishing-schedule.json

Requirements:
  pip install markdown python-frontmatter

The publishing-schedule.json maps slug → publish date and category.
See PUBLISHING.md for the full schedule.
"""

import argparse
import json
import os
import re
import site
import sys
from pathlib import Path

# Ensure user site-packages are on the path (fixes macOS system Python issues)
sys.path.insert(0, site.getusersitepackages())

try:
    import frontmatter
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.toc import TocExtension
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "markdown", "python-frontmatter", "pyyaml"])
    import frontmatter
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.toc import TocExtension

# ── Publishing schedule (slug → date + category) ──────────────────────────────
# Update dates if your calendar changes.
SCHEDULE = {
    "non-toxic-swimwear":                      {"date": "2026-06-24", "category": "pfas"},
    "best-low-tox-summer-fabrics":             {"date": "2026-06-26", "category": "fabrics"},
    "do-leggings-release-microplastics":       {"date": "2026-07-01", "category": "microplastics"},
    "linen-vs-cotton-vs-hemp-summer":          {"date": "2026-07-03", "category": "fabrics"},
    "pfas-clothing-laws-by-state":             {"date": "2026-07-07", "category": "pfas"},
    "fabrics-that-dont-shed-microplastics":    {"date": "2026-07-09", "category": "microplastics"},
    "best-breathable-fabrics":                 {"date": "2026-07-14", "category": "fabrics"},
    "are-quick-dry-clothes-pfas-free":         {"date": "2026-07-16", "category": "pfas"},
    "fabric-construction-microfiber-shedding": {"date": "2026-07-21", "category": "microplastics"},
    "best-fabrics-for-sensitive-skin":         {"date": "2026-07-23", "category": "fabrics"},
    "how-to-spot-pfas-in-product-descriptions":{"date": "2026-07-28", "category": "pfas"},
    "workout-clothes-less-microfiber-shedding":{"date": "2026-07-30", "category": "microplastics"},
    "what-makes-a-fabric-non-toxic":           {"date": "2026-08-04", "category": "fabrics"},
    "pfas-in-performance-fabrics":             {"date": "2026-08-06", "category": "pfas"},
    "reduce-microplastics-from-laundry":       {"date": "2026-08-11", "category": "microplastics"},
    "sustainable-fabric-blends-explained":     {"date": "2026-08-13", "category": "fabrics"},
    "how-to-choose-safer-everyday-basics":     {"date": "2026-08-18", "category": "shopping"},
    "do-fleece-jackets-shed-microplastics":    {"date": "2026-08-20", "category": "microplastics"},
    "natural-vs-synthetic-fabrics-activewear": {"date": "2026-08-25", "category": "fabrics"},
    "questions-before-buying-synthetic-clothing":{"date":"2026-08-27","category":"shopping"},
    "pfas-free-swimwear-beach-cover-ups":      {"date": "2026-09-01", "category": "pfas"},
    "how-to-wash-synthetics-safely":           {"date": "2026-09-03", "category": "microplastics"},
    "best-fabrics-for-everyday-layering":      {"date": "2026-09-08", "category": "fabrics"},
    "how-to-read-fiber-content-clothing-labels":{"date":"2026-09-10","category":"shopping"},
    "best-fabrics-summer-layers":              {"date": "2026-09-15", "category": "fabrics"},
    "best-fabrics-for-sweaty-workouts":        {"date": "2026-09-17", "category": "fabrics"},
    "safer-clothing-checklist":                {"date": "2026-09-22", "category": "shopping"},
}

CATEGORY_LABELS = {
    "pfas":          "PFAS & Fabric Safety",
    "fabrics":       "Fabric Guide",
    "microplastics": "Microplastics",
    "shopping":      "Shopping Guide",
}


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s)
    return s


def parse_md_file(filepath: Path):
    """Parse frontmatter + body from a markdown file."""
    raw = filepath.read_text(encoding="utf-8")
    try:
        post = frontmatter.loads(raw)
        meta = dict(post.metadata)
        body = post.content
    except Exception:
        # Fallback: manual frontmatter parse
        meta = {}
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
                body = parts[2].strip()
    return meta, body


def md_to_html(md_text: str) -> str:
    """Convert markdown to HTML with extensions."""
    # Strip leading H1 (the template already renders the title)
    md_text = re.sub(r'^#\s+.+\n', '', md_text.lstrip(), count=1)
    # Replace unfilled placeholders
    md_text = md_text.replace('{{APPSTORE_LINK}}', 'https://apps.apple.com/us/app/wove-score/id6755356871')

    md = markdown.Markdown(extensions=[
        TableExtension(),
        TocExtension(anchorlink=True),
        "fenced_code",
        "nl2br",
        "smarty",
    ])
    html = md.convert(md_text)
    # Wrap first <p> with drop-cap class
    html = html.replace("<p>", '<p class="drop-cap">', 1)
    return html


def extract_excerpt(body_md: str, max_chars: int = 160) -> str:
    """First non-heading paragraph, stripped of markdown."""
    for line in body_md.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
            clean = re.sub(r'[*_`]', '', clean)
            return clean[:max_chars] + ("…" if len(clean) > max_chars else "")
    return ""


def guess_slug(filepath: Path, meta: dict) -> str:
    """Derive slug from frontmatter or filename."""
    slug = meta.get("slug") or meta.get("canonical", "")
    if slug:
        slug = slug.rstrip("/").rsplit("/", 1)[-1]
    if not slug:
        slug = filepath.stem
    return slugify(slug)


def derive_eyebrow(category: str, meta: dict) -> str:
    label = CATEGORY_LABELS.get(category, "Wove Blog")
    # pull secondary tag from frontmatter tags if present
    tags = meta.get("tags", [])
    if tags and isinstance(tags, list):
        secondary = tags[0].title()
        return f"{label} · {secondary}"
    return label


SLUG_TITLES = {
    "non-toxic-swimwear":                       "Non-Toxic Swimwear: What to Look for Before You Buy",
    "best-low-tox-summer-fabrics":              "The Best Low-Tox Summer Fabrics",
    "do-leggings-release-microplastics":        "Do Leggings Release Microplastics?",
    "linen-vs-cotton-vs-hemp-summer":           "Linen vs. Cotton vs. Hemp for Summer",
    "pfas-clothing-laws-by-state":              "PFAS Clothing Laws by State",
    "fabrics-that-dont-shed-microplastics":     "Fabrics That Don't Shed Microplastics",
    "best-breathable-fabrics":                  "The Best Breathable Fabrics for Hot Weather",
    "are-quick-dry-clothes-pfas-free":          "Are Quick-Dry Clothes PFAS-Free?",
    "fabric-construction-microfiber-shedding":  "How Fabric Construction Affects Microfiber Shedding",
    "best-fabrics-for-sensitive-skin":          "Best Fabrics for Sensitive Skin",
    "how-to-spot-pfas-in-product-descriptions": "How to Spot PFAS in Product Descriptions",
    "workout-clothes-less-microfiber-shedding": "Workout Clothes That Shed Fewer Microfibers",
    "what-makes-a-fabric-non-toxic":            "What Makes a Fabric Non-Toxic?",
    "pfas-in-performance-fabrics":              "PFAS in Performance Fabrics",
    "reduce-microplastics-from-laundry":        "How to Reduce Microplastics from Laundry",
    "sustainable-fabric-blends-explained":      "Sustainable Fabric Blends Explained",
    "how-to-choose-safer-everyday-basics":      "How to Choose Safer Everyday Basics",
    "do-fleece-jackets-shed-microplastics":     "Do Fleece Jackets Shed Microplastics?",
    "natural-vs-synthetic-fabrics-activewear":  "Natural vs. Synthetic Fabrics for Activewear",
    "questions-before-buying-synthetic-clothing":"Questions to Ask Before Buying Synthetic Clothing",
    "pfas-free-swimwear-beach-cover-ups":       "PFAS-Free Swimwear & Beach Cover-Ups",
    "how-to-wash-synthetics-safely":            "How to Wash Synthetics Safely",
    "best-fabrics-for-everyday-layering":       "Best Fabrics for Everyday Layering",
    "how-to-read-fiber-content-clothing-labels":"How to Read Fiber Content Clothing Labels",
    "best-fabrics-summer-layers":               "Best Fabrics for Summer Layers",
    "best-fabrics-for-sweaty-workouts":         "Best Fabrics for Sweaty Workouts",
    "safer-clothing-checklist":                 "Safer Clothing Checklist",
}


def build_related(slug: str, category: str) -> list:
    """Return 2 related post slugs from same category."""
    same_cat = [s for s, v in SCHEDULE.items() if v["category"] == category and s != slug]
    same_cat_sorted = sorted(same_cat, key=lambda s: SCHEDULE[s]["date"])
    related = []
    for rs in same_cat_sorted[:2]:
        related.append({
            "slug":  rs,
            "title": SLUG_TITLES.get(rs, rs.replace("-", " ").title()),
            "cat":   CATEGORY_LABELS.get(category, "Wove Blog"),
        })
    return related


def convert_post(filepath: Path, out_manifests: Path, out_bodies: Path, verbose: bool = True):
    meta, body_md = parse_md_file(filepath)

    slug = guess_slug(filepath, meta)
    if slug not in SCHEDULE:
        if verbose:
            print(f"  ⚠ '{slug}' not in schedule — skipping. Add it to SCHEDULE dict.")
        return

    sched    = SCHEDULE[slug]
    date_str = sched["date"]
    category = sched["category"]

    title = (
        meta.get("title")
        or meta.get("h1")
        or slug.replace("-", " ").title()
    )
    description = meta.get("meta_description") or meta.get("description") or ""
    lede        = meta.get("lede") or description
    eyebrow     = derive_eyebrow(category, meta)
    hero_alt    = meta.get("hero_alt") or f"Illustration for: {title}"
    related     = build_related(slug, category)

    # Convert body
    body_html = md_to_html(body_md)
    excerpt   = extract_excerpt(body_md)

    # Build manifest
    manifest = {
        "slug":        slug,
        "date":        date_str,
        "category":    category,
        "title":       title,
        "description": description,
        "lede":        lede,
        "eyebrow":     eyebrow,
        "excerpt":     excerpt,
        "hero_alt":    hero_alt,
        "related_posts": related,
        "published":   False,
    }

    prefix = f"{date_str}-{slug}"
    manifest_path = out_manifests / f"{prefix}.json"
    body_path     = out_bodies    / f"{prefix}-body.html"

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    body_path.write_text(body_html, encoding="utf-8")

    if verbose:
        print(f"  ✓ {slug}  ({date_str})")


def main():
    parser = argparse.ArgumentParser(description="Convert markdown posts to scheduled HTML")
    parser.add_argument("--posts-dir", default="./drive-exports",
                        help="Directory containing downloaded .md files from Drive")
    parser.add_argument("--out", default=".",
                        help="Repo root (default: current directory)")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    posts_dir    = Path(args.posts_dir)
    repo_root    = Path(args.out)
    out_manifests = repo_root / "_scheduled" / "manifests"
    out_bodies    = repo_root / "_scheduled" / "bodies"
    out_manifests.mkdir(parents=True, exist_ok=True)
    out_bodies.mkdir(parents=True, exist_ok=True)

    md_files = sorted(posts_dir.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {posts_dir}")
        sys.exit(1)

    print(f"Converting {len(md_files)} posts from {posts_dir} …\n")
    for f in md_files:
        convert_post(f, out_manifests, out_bodies, verbose=args.verbose)

    print(f"\nDone. Check _scheduled/manifests/ and _scheduled/bodies/")
    print("Then review each manifest's 'related_posts' titles and update hero_alt if needed.")


if __name__ == "__main__":
    main()

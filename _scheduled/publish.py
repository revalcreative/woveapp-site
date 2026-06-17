#!/usr/bin/env python3
"""
Wove Blog Auto-Publisher
Reads manifests from _scheduled/manifests/, publishes due posts to blog/{slug}/,
and injects cards into blog/index.html.

Usage:
  python3 _scheduled/publish.py --date=YYYY-MM-DD [--dry-run=true]
"""

import argparse
import json
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
MANIFESTS    = ROOT / "_scheduled" / "manifests"
BODIES       = ROOT / "_scheduled" / "bodies"
PUBLISHED    = ROOT / "_scheduled" / "published"
TEMPLATE     = ROOT / "_scheduled" / "post-template.html"
BLOG_INDEX   = ROOT / "blog" / "index.html"
BLOG_DIR     = ROOT / "blog"
LOG_FILE     = ROOT / "_scheduled" / "published-log.json"
COMMIT_MSG   = Path("/tmp/publish-commit-msg.txt")

# ── Category → section mapping ─────────────────────────────────────────────────
SECTION_MAP = {
    "pfas":          "PFAS",
    "fabrics":       "FABRICS",
    "microplastics": "MICROPLASTICS",
    "shopping":      "SHOPPING",
}

CATEGORY_LABELS = {
    "pfas":          "PFAS & Fabric Safety",
    "fabrics":       "Fabric Guide",
    "microplastics": "Microplastics",
    "shopping":      "Shopping Guide",
}

def load_template():
    return TEMPLATE.read_text(encoding="utf-8")


def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []


def save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2))


def format_pub_date(date_str: str) -> str:
    """'2026-06-24' → 'June 2026'"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%B %Y")


def estimate_read_time(body_html: str) -> str:
    words = len(re.sub(r"<[^>]+>", " ", body_html).split())
    minutes = max(1, round(words / 200))
    return f"{minutes} min read"


def build_post_html(manifest: dict, body_html: str, template: str) -> str:
    slug        = manifest["slug"]
    title       = manifest["title"]
    description = manifest["description"]
    eyebrow     = manifest.get("eyebrow", "Wove Blog")
    lede        = manifest.get("lede", description)
    pub_date    = format_pub_date(manifest["date"])
    read_time   = estimate_read_time(body_html)
    hero_alt    = manifest.get("hero_alt", title)
    related     = manifest.get("related_posts", [])

    # Build related posts HTML (up to 2)
    related_html = ""
    for rp in related[:2]:
        related_html += f"""      <a href="/blog/{rp['slug']}/" class="related-card">
        <div class="related-cat">{rp.get('cat', 'Wove Blog')}</div>
        <div class="related-title">{rp['title']}</div>
      </a>\n"""

    replacements = {
        "{{TITLE}}":        title,
        "{{SLUG}}":         slug,
        "{{DESCRIPTION}}":  description,
        "{{EYEBROW}}":      eyebrow,
        "{{LEDE}}":         lede,
        "{{READ_TIME}}":    read_time,
        "{{PUB_DATE}}":     pub_date,
        "{{HERO_ALT}}":     hero_alt,
        "{{BODY}}":         body_html,
        "{{RELATED}}":      related_html,
    }
    html = template
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html


def build_card_html(manifest: dict) -> str:
    slug      = manifest["slug"]
    title     = manifest["title"]
    cat_key   = manifest.get("category", "fabrics")
    cat_label = CATEGORY_LABELS.get(cat_key, "Wove Blog")
    excerpt   = manifest.get("excerpt", manifest.get("description", ""))
    pub_date  = format_pub_date(manifest["date"])
    hero_alt  = manifest.get("hero_alt", title)

    return f"""        <a href="/blog/{slug}/" class="blog-card">
          <div class="blog-card-image">
            <img src="/images/{slug}.png" alt="{hero_alt}" loading="lazy" onerror="this.parentElement.style.display='none'">
          </div>
          <div class="blog-card-body">
            <div class="blog-card-cat">{cat_label}</div>
            <div class="blog-card-title">{title}</div>
            <div class="blog-card-excerpt">{excerpt}</div>
            <div class="blog-card-meta">
              <span>By Emily Hemphill</span><span>·</span><span>{pub_date}</span>
            </div>
          </div>
        </a>"""


def inject_card(index_html: str, card_html: str, section_key: str) -> str:
    """Insert card_html immediately after <!-- INJECT:{SECTION}:START -->"""
    marker = f"<!-- INJECT:{section_key}:START -->"
    if marker not in index_html:
        print(f"  ⚠ Marker '{marker}' not found in blog/index.html — skipping card injection")
        return index_html
    return index_html.replace(marker, marker + "\n" + card_html, 1)


def inject_recent_card(index_html: str, card_html: str) -> str:
    """Insert into the Recent section (replaces oldest if > 2 cards)"""
    marker = "<!-- INJECT:RECENT:START -->"
    end_marker = "<!-- INJECT:RECENT:END -->"
    if marker not in index_html:
        return index_html

    start = index_html.find(marker) + len(marker)
    end   = index_html.find(end_marker)
    current_block = index_html[start:end]

    # Find existing cards
    existing_cards = re.findall(r'(<a href="/blog/[^"]+/" class="blog-card">.*?</a>)', current_block, re.DOTALL)
    # Keep only the most recent 1 (new card becomes slot 1, previous slot 1 becomes slot 2)
    new_block = "\n" + card_html + "\n"
    if existing_cards:
        new_block += existing_cards[0] + "\n"  # carry forward previous newest

    return index_html[:start] + new_block + index_html[end:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=str(date.today()))
    parser.add_argument("--dry-run", default="false")
    args = parser.parse_args()

    today   = args.date
    dry_run = args.dry_run.lower() == "true"

    print(f"🗓  Publishing for date: {today}  |  dry-run: {dry_run}")

    if not MANIFESTS.exists():
        print("No _scheduled/manifests/ directory found — nothing to publish.")
        COMMIT_MSG.write_text("chore: no posts due today")
        return

    due = []
    for jf in sorted(MANIFESTS.glob("*.json")):
        m = json.loads(jf.read_text())
        if m.get("date", "9999") <= today and not m.get("published", False):
            due.append((jf, m))

    if not due:
        print("No posts due today.")
        COMMIT_MSG.write_text("chore: no posts due today")
        return

    template   = load_template()
    index_html = BLOG_INDEX.read_text(encoding="utf-8")
    log        = load_log()
    published_slugs = []

    for jf, manifest in due:
        slug = manifest["slug"]
        body_file = BODIES / f"{manifest['date']}-{slug}-body.html"

        if not body_file.exists():
            print(f"  ⚠ Body file missing: {body_file} — skipping {slug}")
            continue

        print(f"  📄 Publishing: {slug}")
        body_html = body_file.read_text(encoding="utf-8")

        # Build full post HTML
        post_html = build_post_html(manifest, body_html, template)
        post_dir  = BLOG_DIR / slug
        post_path = post_dir / "index.html"

        if not dry_run:
            post_dir.mkdir(parents=True, exist_ok=True)
            post_path.write_text(post_html, encoding="utf-8")
            print(f"     ✓ Written: blog/{slug}/index.html")

        # Build & inject card
        cat_key = manifest.get("category", "fabrics")
        section = SECTION_MAP.get(cat_key, "FABRICS")
        card    = build_card_html(manifest)

        if not dry_run:
            index_html = inject_card(index_html, card, section)
            index_html = inject_recent_card(index_html, card)
            print(f"     ✓ Card injected into #{section.lower()} + #recent")

            # Mark manifest as published and archive it
            manifest["published"] = True
            manifest["published_at"] = today
            jf.write_text(json.dumps(manifest, indent=2))
            PUBLISHED.mkdir(parents=True, exist_ok=True)
            shutil.move(str(jf), str(PUBLISHED / jf.name))

            # Log
            log.insert(0, {"slug": slug, "date": manifest["date"], "title": manifest["title"]})

        published_slugs.append(slug)

    if published_slugs and not dry_run:
        BLOG_INDEX.write_text(index_html, encoding="utf-8")
        save_log(log)
        slugs_str = ", ".join(published_slugs)
        COMMIT_MSG.write_text(f"publish: {slugs_str}")
        print(f"\n✅ Published {len(published_slugs)} post(s): {slugs_str}")
    elif dry_run:
        print(f"\n[DRY RUN] Would publish: {', '.join(published_slugs)}")
        COMMIT_MSG.write_text("chore: dry run — no changes")
    else:
        COMMIT_MSG.write_text("chore: no posts due today")


if __name__ == "__main__":
    main()

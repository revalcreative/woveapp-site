# Wove Blog — Automated Publishing Setup

This system publishes scheduled blog posts to `woveapp.com/blog/` automatically on their calendar dates. Once set up, you export posts from Google Drive, run one local script, push to GitHub, and posts go live on schedule.

---

## How it works

```
Google Drive (.md files)
        ↓
convert_posts.py  (run locally, once per batch)
        ↓
_scheduled/manifests/YYYY-MM-DD-{slug}.json
_scheduled/bodies/YYYY-MM-DD-{slug}-body.html
        ↓  (push to GitHub)
GitHub Action runs daily at 9 AM ET
        ↓
publish.py checks for due posts
        ↓
blog/{slug}/index.html  +  blog/index.html updated
        ↓  (committed + pushed automatically)
woveapp.com/blog/{slug}/  goes live
```

---

## One-time repo setup

### 1. Create a Personal Access Token (PAT)

1. Go to GitHub → Settings → Developer Settings → Personal access tokens → Fine-grained tokens
2. Click **Generate new token**
3. Set expiration (1 year is fine)
4. Repository access: **Only select repositories** → `revalcreative/woveapp-site`
5. Repository permissions: **Contents → Read and write**
6. Click **Generate token** and copy it

### 2. Add the token as a repo secret

1. Go to `github.com/revalcreative/woveapp-site` → Settings → Secrets and variables → Actions
2. Click **New repository secret**
3. Name: `PUBLISH_TOKEN`
4. Value: paste the token
5. Click **Add secret**

### 3. Copy these files into the repo

Copy everything from this `github-action-setup/` folder into the root of `woveapp-site/`:

```
.github/workflows/publish-posts.yml   → automated cron trigger
_scheduled/publish.py                 → publish script (runs in the Action)
_scheduled/post-template.html         → HTML wrapper for new posts
_scheduled/convert_posts.py           → converts Drive markdown to scheduled format
blog/index.html                       → REPLACE existing blog/index.html (adds injection markers + Microplastics section)
PUBLISHING.md                         → this file
```

**Important:** `blog/index.html` replaces the existing one. It's identical to the current live version except for:
- Injection comment markers (invisible to readers, used by publish.py)
- New "Microplastics" section in the category nav and page body

### 4. Install Python dependencies (local use only)

```bash
pip install markdown python-frontmatter pyyaml
```

---

## Converting posts from Google Drive

### Step 1: Download the markdown files

In Google Drive, open the blog posts folder and download all `.md` files to a local folder, e.g. `~/Downloads/wove-blog-posts/`.

### Step 2: Run the converter

From the repo root:

```bash
python3 _scheduled/convert_posts.py --posts-dir ~/Downloads/wove-blog-posts
```

This creates:
- `_scheduled/manifests/YYYY-MM-DD-{slug}.json` — metadata for each post
- `_scheduled/bodies/YYYY-MM-DD-{slug}-body.html` — article body HTML

### Step 3: Review and edit manifests

Open each `.json` file in `_scheduled/manifests/` and verify:

```json
{
  "slug": "non-toxic-swimwear",
  "date": "2026-06-24",
  "category": "pfas",
  "title": "Non-Toxic Swimwear: ...",
  "description": "...",
  "lede": "...",
  "eyebrow": "PFAS & Fabric Safety",
  "excerpt": "...",
  "hero_alt": "Illustration of ...",
  "related_posts": [
    { "slug": "pfas-clothing-laws-by-state", "title": "PFAS Clothing Laws by State", "cat": "PFAS & Fabric Safety" },
    { "slug": "are-quick-dry-clothes-pfas-free", "title": "Are Quick-Dry Clothes PFAS-Free?", "cat": "PFAS & Fabric Safety" }
  ],
  "published": false
}
```

Key fields to check:
- `title` — should match the H1 in the post
- `lede` — the subtitle/deck shown under the title (pull from the post's intro)
- `eyebrow` — shown above the title (e.g. "PFAS & Fabric Safety · Swimwear")
- `excerpt` — 1-2 sentences for the blog index card
- `hero_alt` — alt text for the hero image (also used in the index card)
- `related_posts` — 2 posts to show at the bottom; update titles to be accurate

### Step 4: Add hero images

Each post needs a hero image at `/images/{slug}.svg` in the repo. The template references it at `/images/{{SLUG}}.svg`. If the image is missing the hero area will be hidden gracefully.

Hero images should be 1200×520px SVG (matching the existing post style). See `blog/pfas-in-activewear/index.html` for a reference inline SVG.

### Step 5: Push everything to GitHub

```bash
git add _scheduled/
git commit -m "chore: add scheduled posts batch [Jun–Sep 2026]"
git push
```

The Action will pick up posts automatically on their publish dates.

---

## Publishing schedule (Jun 23 – Sep 23, 2026)

| Date | Slug | Category |
|------|------|----------|
| Jun 24 | non-toxic-swimwear | PFAS |
| Jun 26 | best-low-tox-summer-fabrics | Fabrics |
| Jul 1 | do-leggings-release-microplastics | Microplastics |
| Jul 3 | linen-vs-cotton-vs-hemp-summer | Fabrics |
| Jul 7 | pfas-clothing-laws-by-state | PFAS |
| Jul 9 | fabrics-that-dont-shed-microplastics | Microplastics |
| Jul 14 | best-breathable-fabrics | Fabrics |
| Jul 16 | are-quick-dry-clothes-pfas-free | PFAS |
| Jul 21 | fabric-construction-microfiber-shedding | Microplastics |
| Jul 23 | best-fabrics-for-sensitive-skin | Fabrics |
| Jul 28 | how-to-spot-pfas-in-product-descriptions | PFAS |
| Jul 30 | workout-clothes-less-microfiber-shedding | Microplastics |
| Aug 4 | what-makes-a-fabric-non-toxic | Fabrics |
| Aug 6 | pfas-in-performance-fabrics | PFAS |
| Aug 11 | reduce-microplastics-from-laundry | Microplastics |
| Aug 13 | sustainable-fabric-blends-explained | Fabrics |
| Aug 18 | how-to-choose-safer-everyday-basics | Shopping |
| Aug 20 | do-fleece-jackets-shed-microplastics | Microplastics |
| Aug 25 | natural-vs-synthetic-fabrics-activewear | Fabrics |
| Aug 27 | questions-before-buying-synthetic-clothing | Shopping |
| Sep 1 | pfas-free-swimwear-beach-cover-ups | PFAS |
| Sep 3 | how-to-wash-synthetics-safely | Microplastics |
| Sep 8 | best-fabrics-for-everyday-layering | Fabrics |
| Sep 10 | how-to-read-fiber-content-clothing-labels | Shopping |
| Sep 15 | best-fabrics-summer-layers | Fabrics |
| Sep 17 | best-fabrics-for-sweaty-workouts | Fabrics |
| Sep 22 | safer-clothing-checklist | Shopping |

---

## Triggering a publish manually

In GitHub → Actions → "Publish Scheduled Blog Posts" → **Run workflow**

Set `dry_run = true` to preview which posts would publish without committing anything.

---

## Troubleshooting

**Action runs but nothing publishes**
- Check that manifest files are in `_scheduled/manifests/` (not `_scheduled/` root)
- Check that body files are in `_scheduled/bodies/`
- Check the manifest `date` field is ≤ today and `published` is `false`

**Post publishes but card doesn't appear in blog/index.html**
- Check that the injection markers exist in `blog/index.html` (e.g. `<!-- INJECT:PFAS:START -->`)
- Check that the `category` field in the manifest matches one of: `pfas`, `fabrics`, `microplastics`, `shopping`

**Wrong HTML in post**
- Edit the body HTML in `_scheduled/bodies/YYYY-MM-DD-{slug}-body.html` directly
- Or re-run `convert_posts.py` after editing the source markdown

**Republish a post after fixing it**
- Set `"published": false` in the archived manifest (in `_scheduled/published/`)
- Move the manifest back to `_scheduled/manifests/`
- Delete `blog/{slug}/index.html` from the repo
- Run workflow manually

---

## File structure reference

```
woveapp-site/
├── .github/
│   └── workflows/
│       └── publish-posts.yml       ← GitHub Action (cron + manual trigger)
├── _scheduled/
│   ├── publish.py                  ← publish script
│   ├── post-template.html          ← HTML wrapper for new posts
│   ├── convert_posts.py            ← local helper: md → scheduled files
│   ├── published-log.json          ← auto-created: record of published posts
│   ├── manifests/                  ← one JSON per pending post
│   │   └── 2026-06-24-non-toxic-swimwear.json
│   ├── bodies/                     ← one HTML body per pending post
│   │   └── 2026-06-24-non-toxic-swimwear-body.html
│   └── published/                  ← manifests moved here after publishing
├── blog/
│   ├── index.html                  ← blog index (has injection markers)
│   ├── pfas-in-activewear/
│   │   └── index.html
│   └── {slug}/                     ← created by publish.py on publish date
│       └── index.html
└── images/
    └── {slug}.svg                  ← hero images (one per post — add manually)
```

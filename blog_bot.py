#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feathered Gossip blog bot - svaki dan napiše jedan članak o jednoj ptici i ponovo izgradi ceo sajt.

Tok jednog članka:
  0. SHOP: jednom nedeljno preko Apify-ja pročita tvoj Redbubble shop (naziv dizajna, tagovi, slika, link) i prepozna
     koja je ptica na svakom dizajnu. Rezultat čuva u data/shop.json, pa ostale dane ne troši ništa.
  1. Bira DIZAJN iz shopa koji još nije imao članak (noviji prvo) i UGAO članka za tu pticu (prepoznavanje,
     zanimljive činjenice, dvorište, ponašanje, pesma, gnežđenje, slične vrste, pokloni pred praznike...).
     Bez Apify ključa bira pticu sa spiska i linkuje ceo shop.
  2. ISTRAŽIVANJE: Gemini sa Google pretragom skupi proverene činjenice (RSPB, BTO, Cornell Lab, Audubon...).
  3. PISANJE: Gemini napiše članak SAMO iz tih činjenica, u JSON obliku (naslov, opis, sekcije, brze činjenice, FAQ).
     Kod proveri dužinu, naslov, linkove, zabranjene AI fraze i izmišljena lična iskustva.
  4. PROVERA ČINJENICA: drugi Gemini poziv sa Google pretragom traži netačne tvrdnje; ako ih nađe, članak se ispravlja.
  5. SLIKA: naslovna slika je TVOJ DIZAJN iz shopa na kartici u bojama brenda (1200x675, za Google Discover mora
     >= 1200 px širine). Ako slika dizajna ne može da se preuzme, Fal.ai nacrta ilustraciju u stilu brenda.
  6. Ceo sajt se ponovo gradi u folder site/: članci, početna, blog, stranice ptica, sitemap.xml, feed.xml, robots.txt.

Pokretanje:
  python blog_bot.py              -> napiše POSTS_PER_RUN članaka (podrazumevano 1) i izgradi sajt
  python blog_bot.py --rebuild    -> samo ponovo izgradi sajt (posle izmene site_config.json, shop_birds.txt ili izgleda)

Environment promenljive:
  GEMINI_API_KEY (obavezno)   APIFY_TOKEN (čitanje Redbubble shopa)   FAL_KEY (rezervna slika, opciono)
  SHOP_REFRESH=1 (osveži spisak dizajna odmah, ne čekaj nedelju dana)
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (opciono, javlja kad izađe članak)
  POSTS_PER_RUN=1   BIRD=...   ANGLE=...   (BIRD/ANGLE: ručno izaberi temu, npr. BIRD="blue tit" ANGLE=facts)
"""
import os
import re
import sys
import json
import html
import math
import time
import random
import shutil
import datetime
import unicodedata
from io import BytesIO
from collections import Counter, defaultdict
from urllib.parse import quote_plus, urlparse

import requests
from PIL import Image

try:
    from google import genai
    from google.genai import types
except ImportError:          # dozvoljava --rebuild bez instaliranog google-genai
    genai = types = None

from birds_data import BIRDS, SEASONS

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data", "posts")
ASSETS_SRC = os.path.join(ROOT, "assets")
IMG_DIR = os.path.join(SITE_DIR, "blog", "images")

with open(os.path.join(ROOT, "site_config.json"), encoding="utf-8") as _f:
    CONFIG = json.load(_f)

SITE_NAME = CONFIG.get("site_name", "Feathered Gossip")
TAGLINE = CONFIG.get("tagline", "Birds with opinions.")
SITE_URL = (os.getenv("SITE_URL") or CONFIG["site_url"]).rstrip("/")
BASE = urlparse(SITE_URL).path.rstrip("/")          # "" za korisnički sajt, "/repo" za sajt projekta
RB_USER = CONFIG["redbubble_user"]
SHOP_URL = CONFIG.get("shop_url") or f"https://www.redbubble.com/people/{RB_USER}/shop"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
FAL_KEY = os.getenv("FAL_KEY", "")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
APIFY_ACTOR = os.getenv("APIFY_ACTOR") or CONFIG.get("apify_actor", "solidcode~redbubble-com-scraper")
SHOP_FILE = os.path.join(ROOT, "data", "shop.json")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


POSTS_PER_RUN = max(0, min(3, env_int("POSTS_PER_RUN", 1)))   # Google kažnjava masovno pravljene stranice: max 3
AVAILABLE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash'
]
IMG_W, IMG_H = 1200, 675

# Imena koja ljudi stvarno kucaju (za naslov i ključne reči)
DISPLAY_NAMES = {
    "bullfinch": "Bullfinch", "wren": "Wren", "magpie": "Magpie", "crow": "Crow", "jackdaw": "Jackdaw",
    "goldcrest": "Goldcrest", "mallard": "Mallard", "shoebill": "Shoebill", "flamingo": "Flamingo",
    "common blackbird": "Blackbird", "common starling": "Starling", "common kingfisher": "Kingfisher",
    "common raven": "Raven", "rock pigeon": "Rock Pigeon",
}
SEARCH_HINTS = {
    "european robin": 'In the UK people simply say "robin"; never confuse it with the American robin (a thrush).',
    "american robin": "It is a thrush, not related to the European robin.",
    "common blackbird": 'In the UK it is just "blackbird"; it is a thrush, unrelated to American blackbirds.',
    "crow": "Write about the crow the reader most likely sees in their region; make clear which species you mean.",
    "magpie": "This is the Eurasian magpie (Pica pica).",
}

TRUSTED_SOURCES = {
    "rspb": ("RSPB", "https://www.rspb.org.uk/"),
    "bto": ("BTO", "https://www.bto.org/"),
    "cornell": ("Cornell Lab of Ornithology (All About Birds)", "https://www.allaboutbirds.org/"),
    "all about birds": ("Cornell Lab of Ornithology (All About Birds)", "https://www.allaboutbirds.org/"),
    "audubon": ("National Audubon Society", "https://www.audubon.org/"),
    "birds of the world": ("Birds of the World", "https://birdsoftheworld.org/"),
    "wildlife trust": ("The Wildlife Trusts", "https://www.wildlifetrusts.org/"),
    "iucn": ("IUCN Red List", "https://www.iucnredlist.org/"),
    "birdlife": ("BirdLife International", "https://www.birdlife.org/"),
    "woodland trust": ("Woodland Trust", "https://www.woodlandtrust.org.uk/"),
    "national geographic": ("National Geographic", "https://www.nationalgeographic.com/animals/"),
    "smithsonian": ("Smithsonian", "https://www.si.edu/"),
    "usgs": ("USGS", "https://www.usgs.gov/"),
    "fish and wildlife": ("U.S. Fish & Wildlife Service", "https://www.fws.gov/"),
    "ebird": ("eBird", "https://ebird.org/"),
    "xeno-canto": ("xeno-canto", "https://xeno-canto.org/"),
}

ANGLES = {
    "identification": {
        "keyword": "{bird} identification",
        "goal": "a practical identification guide: size and shape, male/female/juvenile plumage, the call and song "
                "described in words, behaviour that gives it away, and how to tell it apart from look-alikes.",
        "title": 'e.g. "How to Identify a {Name}: Field Marks, Song and Look-Alikes"',
    },
    "facts": {
        "keyword": "{bird} facts",
        "goal": "a list-style article of 10-15 surprising, specific, true facts (each fact its own H2 or a numbered "
                "H2), each explained in 2-4 sentences with the 'why'.",
        "title": 'e.g. "13 Surprising {Name} Facts (Most People Get #4 Wrong)" - no clickbait lies, the number must '
                 'match the number of facts',
    },
    "garden": {
        "keyword": "how to attract {bird}s to your {garden}",
        "goal": "a practical how-to: the right food and feeders, water, planting, nest boxes or nesting sites, "
                "timing through the year, and common mistakes. Only advice supported by the research notes.",
        "title": 'e.g. "How to Attract {Name}s to Your {Garden_cap}: Food, Feeders and Nest Boxes"',
    },
    "where": {
        "keyword": "where to see {bird}s",
        "goal": "where and when to see this bird in the wild: range, habitat, best months and time of day, "
                "responsible viewing, and how to find it with binoculars.",
        "title": 'e.g. "Where to See a {Name} in the Wild (and When to Go)"',
    },
    "behavior": {
        "keyword": "{bird} behavior",
        "goal": "the bird's quirky, opinionated behaviour explained: why it does what it does (territory, courtship, "
                "feeding tricks, calls, social life), with the science behind each habit. This is where the "
                "'birds with opinions' humour shines, but every claim must be true.",
        "title": 'e.g. "Why Do {Name}s Do That? {N} Odd Behaviours Explained"',
    },
    "song": {
        "keyword": "{bird} song and call",
        "goal": "a guide to the bird's voice: what the song and the main calls sound like (described in words and "
                "memorable mnemonics from the notes), when and why it sings, differences between male and female, "
                "and how to tell it from similar-sounding birds.",
        "title": 'e.g. "What Does a {Name} Sound Like? Song, Calls and What They Mean"',
    },
    "nesting": {
        "keyword": "{bird} nesting",
        "goal": "the breeding season: courtship, nest site and building, eggs and incubation, chicks and fledglings, "
                "number of broods, and how people can help (or should leave nests alone).",
        "title": 'e.g. "{Name} Nesting: From First Twig to Fledgling"',
    },
    "lookalikes": {
        "keyword": "{bird} vs look-alikes",
        "goal": "how to tell this bird apart from the species it is most often confused with: side-by-side field "
                "marks, voice, behaviour, habitat and range. Only species named in the research notes.",
        "title": 'e.g. "{Name} or Not? How to Tell It From Its Look-Alikes"',
    },
    "folklore": {
        "keyword": "{bird} meaning and folklore",
        "goal": "the bird in culture: the origin of its name, old local names, folklore, superstitions, symbolism, "
                "literature and art, clearly separating legend from biology. Only facts from the notes.",
        "title": 'e.g. "{Name} Meaning: Folklore, Symbolism and the Real Bird Behind the Myths"',
    },
    "gifts": {
        "keyword": "{bird} gifts for bird lovers",
        "goal": "a helpful gift guide for people who love this bird: explain what makes the bird special (true facts) "
                "and why fans love it, then give ideas by recipient and budget, mixing our designs (stickers, "
                "t-shirts, hoodies) with genuinely useful birding gifts in general terms (field guide, feeder, nest "
                "box, binoculars). Do not invent product names, prices or brands.",
        "title": 'e.g. "{Name} Gifts for Bird Lovers: {N} Ideas They Will Actually Use"',
    },
}
GIFT_WINDOWS = [((11, 1), (12, 18)), ((4, 20), (5, 10)), ((5, 25), (6, 14))]   # Božić, Majčin dan (US), Očev dan

BANNED_PHRASES = [
    "delve", "tapestry", "in conclusion", "look no further", "whether you're a seasoned", "in today's",
    "unleash", "elevate your", "testament to", "a must-have", "game-changer", "game changer", "dive into",
    "navigating the", "embark on", "treasure trove", "it's important to note", "in the realm of", "bustling",
    "nestled", "symphony of", "vibrant tapestry", "plethora", "furthermore,", "moreover,", "rest assured",
    "without further ado", "as an ai", "i cannot",
]
FAKE_EXPERIENCE_RE = re.compile(
    r"(?i)\b(I|we)\s+(once\s+)?(saw|spotted|watched|heard|found|photographed|have seen|have watched|"
    r"have spotted|remember|tested|tried)\b|\b(my|our)\s+(garden|backyard|feeder|binoculars|local patch)\b")
TOKEN_RE = re.compile(r"\[\[(stickers|tees|hoodies|designs|design|shop|post:[a-z0-9-]+)\|([^\]|]{2,80})\]\]")


# ---------------------------------------------------------------------------
# POMOĆNE
# ---------------------------------------------------------------------------
def redact(text):
    text = str(text)
    for secret in (GEMINI_API_KEY, FAL_KEY, TELEGRAM_BOT_TOKEN, APIFY_TOKEN):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    return text


def esc(text):
    return html.escape(str(text or ""), quote=True)


def slugify(text, limit=70):
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(t) > limit:
        t = t[:limit].rsplit("-", 1)[0]
    return t or "post"


def bird_name(bird):
    if bird in DISPLAY_NAMES:
        return DISPLAY_NAMES[bird]
    return " ".join(w[:1].upper() + w[1:] for w in bird.split())


def bird_slug(bird):
    return slugify(bird)


def bird_info(bird):
    return BIRDS.get(bird, {"region": "world", "palette": set(), "marks": f"the real markings of a {bird}", "seasons": []})


def garden_word(bird):
    return "backyard" if bird_info(bird)["region"] == "na" else "garden"


def region_text(bird):
    return {"uk": "Britain and Europe", "na": "North America", "both": "Britain, Europe and North America",
            "world": "its native range"}[bird_info(bird)["region"]]


def u(path):
    """Interna putanja (radi i za sajt projekta /repo/...)."""
    return BASE + path


def absu(path):
    return SITE_URL + path


def today():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).date()


def nice_date(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d.day} {d.strftime('%B %Y')}"


def http_request(method, url, retries=3, backoff=4, timeout=120, **kwargs):
    last = "nepoznato"
    for attempt in range(1, retries + 1):
        try:
            r = requests.request(method, url, timeout=timeout, **kwargs)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}: {redact(r.text)[:200]}"
            if r.status_code not in {408, 409, 425, 429, 500, 502, 503, 504}:
                break
        except requests.exceptions.RequestException as e:
            last = redact(e)
        if attempt < retries:
            time.sleep(backoff * attempt)
    raise RuntimeError(f"{method} {redact(url)[:80]} nije uspeo: {last}")


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    for opener, closer in (("{", "}"), ("[", "]")):
        s, e = text.find(opener), text.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except ValueError:
                continue
    raise ValueError("Nema validnog JSON-a u odgovoru")


# ---------------------------------------------------------------------------
# GEMINI (isti zaštitni mehanizam kao u botu za dizajne: potrošen model se preskače, preopterećen pauzira)
# ---------------------------------------------------------------------------
_client = None
_MODEL_DEAD = set()
_MODEL_PAUSED = {}


def get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("Nedostaje GEMINI_API_KEY u GitHub Secrets!")
        try:
            _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=120_000))
        except Exception:
            _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _model_failed(model, err):
    msg = str(err)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        if model not in _MODEL_DEAD:
            print(f"    [!] {model}: kvota potrošena -> preskačem ga do kraja pokretanja")
        _MODEL_DEAD.add(model)
    elif any(s in msg for s in ("503", "UNAVAILABLE", "high demand", "disconnected", "timed out", "imeout",
                                "500", "INTERNAL")):
        _MODEL_PAUSED[model] = time.time() + 120


def _models_now():
    alive = [m for m in AVAILABLE_MODELS if m not in _MODEL_DEAD]
    ready = [m for m in alive if _MODEL_PAUSED.get(m, 0) <= time.time()]
    return ready or sorted(alive, key=lambda m: _MODEL_PAUSED.get(m, 0))


def gemini(prompt, json_mode=False, grounded=False, image=None, validator=None, label="gemini"):
    client = get_client()
    contents = prompt
    if image is not None:
        data, mime = image
        contents = [types.Part.from_bytes(data=data, mime_type=mime), prompt]
    cfg = {}
    if grounded:
        cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    elif json_mode:
        cfg["response_mime_type"] = "application/json"
    config = types.GenerateContentConfig(**cfg) if cfg else None
    last_err = None
    models = _models_now()
    if not models:
        raise RuntimeError(f"Svim Gemini modelima je potrošena kvota ({label}).")
    for model in models:
        try:
            kwargs = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config
            resp = client.models.generate_content(**kwargs)
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                raise ValueError("prazan odgovor")
            if validator is not None and not validator(text):
                raise ValueError("odgovor ne prolazi proveru oblika")
            return text
        except Exception as e:
            last_err = e
            _model_failed(model, e)
            if model not in _MODEL_DEAD:
                print(f"    [!] {label}: model {model} nije uspeo ({redact(e)[:120]}). Sledeći...")
            time.sleep(1)
    raise RuntimeError(f"Svi Gemini modeli su otkazali ({label}): {redact(last_err)[:200]}")


def json_ok(text):
    try:
        extract_json(text)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# PODACI
# ---------------------------------------------------------------------------
def load_posts():
    posts = []
    if os.path.isdir(DATA_DIR):
        for name in os.listdir(DATA_DIR):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
                        p = json.load(f)
                    if p.get("slug") and p.get("title"):
                        posts.append(p)
                except (OSError, ValueError) as e:
                    print(f"[!] Ne mogu da pročitam {name}: {e}")
    posts.sort(key=lambda p: (p.get("date", ""), p.get("slug")), reverse=True)
    return posts


def save_post(post):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, post["slug"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=1)


def load_shop_birds():
    path = os.path.join(ROOT, "shop_birds.txt")
    birds = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip().lower()
                if line:
                    birds.add(line)
    return birds


SHOP_BIRDS = load_shop_birds()          # ručni spisak + (posle učitavanja shopa) ptice sa dizajnima


def in_shop(bird):
    return bool(bird) and bird.lower() in SHOP_BIRDS


IA_CODES = {"stickers": "all-stickers", "tees": "u-tees", "hoodies": "u-sweatshirts"}


def design_phrase(design):
    return re.split(r"\s+[-–—|]\s+", str(design.get("title", "")).strip(), maxsplit=1)[0].strip()


def rb_search(query, kind=None):
    url = f"https://www.redbubble.com/shop/?query={quote_plus(query)}&artistUserName={RB_USER}"
    return url + (f"&iaCode={IA_CODES[kind]}" if kind in IA_CODES else "")


def rb_link(kind, bird=None, design=None):
    """Linkovi ka shopu.
    design   -> tačno taj dizajn (link proizvoda iz shopa)
    stickers/tees/hoodies/designs -> svi dizajni te ptice u TVOM shopu (ako je ptica u shopu), inače kategorija shopa
    shop     -> ceo shop"""
    if kind == "shop":
        return SHOP_URL
    if kind == "design":
        if design and design.get("url"):
            return design["url"]
        if design:
            return rb_search(design_phrase(design))
        kind = "designs"
    if bird and in_shop(bird):
        return rb_search(bird, None if kind == "designs" else kind)
    if kind == "designs":
        return SHOP_URL
    return f"https://www.redbubble.com/people/{RB_USER}/shop?asc=u&iaCode={IA_CODES[kind]}"


def design_link(design, kind):
    """Isti dizajn kao nalepnica / majica / duks / svi proizvodi (pretraga po nazivu dizajna u tvom shopu)."""
    if kind == "stickers" and design.get("url") and "sticker" in str(design.get("product_type", "")).lower():
        return design["url"]
    return rb_search(design_phrase(design), None if kind == "all" else kind)


# ---------------------------------------------------------------------------
# SHOP: dizajni sa Redbubble-a preko Apify-ja (Redbubble blokira obične botove)
# ---------------------------------------------------------------------------
BIRD_ALIASES = [
    ("chickadee", "black-capped chickadee"), ("cardinal", "northern cardinal"), ("junco", "dark-eyed junco"),
    ("hummingbird", "ruby-throated hummingbird"), ("puffin", "atlantic puffin"), ("kingfisher", "common kingfisher"),
    ("starling", "common starling"), ("raven", "common raven"), ("red winged blackbird", "red-winged blackbird"),
    ("blackbird", "common blackbird"), ("nuthatch", "eurasian nuthatch"), ("goldfinch", "european goldfinch"),
    ("great blue heron", "great blue heron"), ("gray heron", "grey heron"), ("heron", "grey heron"),
    ("titmouse", "tufted titmouse"), ("wagtail", "pied wagtail"), ("eagle", "bald eagle"),
    ("swallow", "barn swallow"), ("waxwing", "cedar waxwing"), ("bluebird", "eastern bluebird"),
    ("mockingbird", "northern mockingbird"), ("dove", "mourning dove"), ("pigeon", "rock pigeon"),
    ("long tailed tit", "long-tailed tit"), ("sparrow", "house sparrow"), ("jenny wren", "wren"),
]
NA_MARKERS = ("american", "backyard", "north american", "usa", "canada")


def _norm(text):
    return " " + re.sub(r"[^a-z0-9 ]+", " ", str(text).lower().replace("-", " ")) + " "


def detect_bird(title, tags):
    text = _norm(title + " " + " ".join(tags or []))
    title_n = _norm(title)
    for key in sorted(BIRDS, key=len, reverse=True):          # najduže ime prvo (great blue heron pre heron)
        k = _norm(key)
        if k in title_n:
            return key
    for key in sorted(BIRDS, key=len, reverse=True):
        if _norm(key) in text:
            return key
    if " robin " in text:
        return "american robin" if any(m in text for m in NA_MARKERS) and "british" not in text else "european robin"
    for alias, key in BIRD_ALIASES:
        if _norm(alias) in text:
            if key == "european goldfinch" and " american " in text:
                return "american goldfinch"
            return key
    return ""


def load_shop():
    try:
        with open(SHOP_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("designs"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"updated": "", "designs": {}}


def save_shop(shop):
    os.makedirs(os.path.dirname(SHOP_FILE), exist_ok=True)
    with open(SHOP_FILE, "w", encoding="utf-8") as f:
        json.dump(shop, f, ensure_ascii=False, indent=1)


def apify_items(shop_url, max_results):
    """Pokrene Apify alat za Redbubble (asinhrono, sa čekanjem) i vrati listu proizvoda."""
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}", "Content-Type": "application/json"}
    payload = {"searchQueries": [], "searchUrls": [shop_url], "maxResults": max_results}
    r = http_request("POST", f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/runs", headers=headers, json=payload,
                     retries=2)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Apify nije pokrenuo alat: HTTP {r.status_code}")
    run = r.json().get("data", {})
    run_id, dataset = run.get("id"), run.get("defaultDatasetId")
    deadline = time.time() + 15 * 60
    status = run.get("status")
    while status not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT") and time.time() < deadline:
        time.sleep(15)
        status = http_request("GET", f"https://api.apify.com/v2/actor-runs/{run_id}", headers=headers).json() \
            .get("data", {}).get("status")
    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify alat nije uspeo (status {status})")
    items = http_request("GET", f"https://api.apify.com/v2/datasets/{dataset}/items?clean=true&format=json",
                         headers=headers).json()
    return items if isinstance(items, list) else []


def _first(item, *keys):
    for k in keys:
        v = item.get(k)
        if isinstance(v, list):
            v = v[0] if v else ""
        if isinstance(v, dict):
            v = v.get("url") or v.get("src") or ""
        if v:
            return str(v)
    return ""


def classify_unknown(designs):
    """Dizajni čiju pticu kod nije prepoznao: jedan Gemini poziv za sve."""
    todo = {k: d for k, d in designs.items() if not d.get("bird") and not d.get("bird_checked")}
    if not todo or not GEMINI_API_KEY or genai is None:
        return
    lines = "\n".join(f'{k}: {d["title"]} | tags: {", ".join(d.get("tags", [])[:15])}' for k, d in todo.items())
    prompt = ("Each line is a print-on-demand design (id: title | tags). Which real bird SPECIES is on each design? "
              "Use the common English name in lowercase (e.g. \"european robin\", \"blue jay\"). If it is not a "
              "bird or the species is unclear, use \"\".\nReturn ONLY JSON {\"id\": \"species\", ...}.\n\n" + lines)
    try:
        res = extract_json(gemini(prompt, json_mode=True, validator=json_ok, label="prepoznavanje ptica"))
    except Exception as e:
        print(f"  [!] Prepoznavanje ptica nije uspelo: {redact(e)[:100]}")
        return
    for k, d in todo.items():
        name = str(res.get(k, "") if isinstance(res, dict) else "").strip().lower()
        d["bird_checked"] = True
        if name and len(name) < 40:
            d["bird"] = detect_bird(name, []) or name


def refresh_shop(force=False):
    """Osvežava spisak dizajna najviše jednom u shop_refresh_days dana (Apify naplaćuje po proizvodu)."""
    shop = load_shop()
    if not APIFY_TOKEN:
        if not shop["designs"]:
            print("ℹ Nema APIFY_TOKEN: bot ne može da čita shop, piše o pticama sa spiska i linkuje ceo shop")
        return shop
    days = float(CONFIG.get("shop_refresh_days", 7))
    try:
        age = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.datetime.fromisoformat(shop["updated"].rstrip("Z"))).days
    except ValueError:
        age = 9999
    if not force and shop["designs"] and age < days:
        print(f"ℹ Spisak dizajna je star {age} dana (osvežava se na {days:g}): {len(shop['designs'])} dizajna")
        return shop
    url = CONFIG.get("shop_scrape_url") or f"https://www.redbubble.com/people/{RB_USER}/shop?asc=u&iaCode=all-stickers"
    print(f"↻ Čitam Redbubble shop preko Apify-ja: {url}")
    try:
        items = apify_items(url, int(CONFIG.get("shop_max_results", 120)))
    except Exception as e:
        print(f"  [!] Shop nije pročitan ({redact(e)[:200]}); koristim stari spisak")
        tg(f"⚠ {SITE_NAME}: Apify nije pročitao shop ({redact(e)[:150]})")
        return shop
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat() + "Z"
    added = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        work = _first(it, "workId", "work_id", "id", "productId") or _first(it, "url")
        title = _first(it, "title", "name")
        url_p = _first(it, "url", "productUrl", "link")
        img = _first(it, "imageUrl", "image", "images", "thumbnail")
        artist_url = _first(it, "artistUrl", "artist_url").lower()
        # čitamo SAMO tvoj shop; preskače se samo ono što očigledno pripada drugom umetniku
        # (artistName može biti i ime shopa "Feathered Gossip", zato se gleda link umetnika)
        if not (work and title and url_p) or (artist_url and f"/people/{RB_USER.lower()}/" not in artist_url + "/"):
            continue
        tags = it.get("tags") if isinstance(it.get("tags"), list) else []
        ptype = _first(it, "productType", "product_type", "type")
        d = shop["designs"].get(work)
        if d is None:
            d = {"id": work, "first_seen": now, "featured": 0}
            shop["designs"][work] = d
            added += 1
        elif "sticker" in str(d.get("product_type", "")).lower() and "sticker" not in ptype.lower():
            continue                     # za isti dizajn zadrži nalepnicu kao glavni proizvod
        d.update({"title": title, "url": url_p, "image_url": img, "tags": [str(t) for t in tags][:30],
                  "product_type": ptype, "last_seen": now})
        if not d.get("bird"):
            d["bird"] = detect_bird(title, d["tags"])
    classify_unknown(shop["designs"])
    shop["updated"] = now
    save_shop(shop)
    birds = Counter(d.get("bird") for d in shop["designs"].values() if d.get("bird"))
    print(f"  ✓ {len(items)} proizvoda, {added} novih dizajna; ptice: {dict(birds.most_common(12))}")
    return shop


def sync_shop_birds(shop):
    for d in shop["designs"].values():
        if d.get("bird"):
            SHOP_BIRDS.add(d["bird"].lower())


# ---------------------------------------------------------------------------
# IZBOR TEME
# ---------------------------------------------------------------------------
def in_window(d, start, end):
    md = (d.month, d.day)
    return start <= md <= end if start <= end else (md >= start or md <= end)


def active_seasons(d):
    return {sid for sid, _, s, e in SEASONS if in_window(d, s, e)}


def gift_season(d):
    return any(in_window(d, s, e) for s, e in GIFT_WINDOWS)


def angles_for(bird, d):
    region = bird_info(bird)["region"]
    order = ["identification", "facts", "where" if region == "world" else "garden", "behavior", "song",
             "lookalikes", "nesting", "folklore"]
    if in_shop(bird):
        # vodič za poklone nikad kao PRVI članak o ptici (Google ne voli sajtove koji su samo prodaja);
        # u sezoni poklona ide odmah posle prvog korisnog članka
        if gift_season(d):
            order.insert(1, "gifts")
        else:
            order.append("gifts")
    return order


def pick_topic(posts, d, shop=None):
    """Vraća (ptica, ugao, dizajn ili None).
    1) dizajn iz shopa koji još nije imao članak (najnoviji prvo), pa dizajni sa najmanje članaka;
    2) bez shopa: ptica sa spiska (prednost: sezona, ptice sa manje članaka)."""
    forced_bird = os.getenv("BIRD", "").strip().lower()
    forced_angle = os.getenv("ANGLE", "").strip().lower()
    used = defaultdict(set)
    for p in posts:
        used[p["bird"]].add(p["angle"])
    recent = [p["bird"] for p in posts[:10]]
    designs = [x for x in ((shop or {}).get("designs") or {}).values() if x.get("bird")]
    seasons = active_seasons(d)

    def next_angle(bird):
        if forced_angle:
            return forced_angle
        return next((a for a in angles_for(bird, d) if a not in used[bird]), None)

    if forced_bird:
        cand = [x for x in designs if x["bird"] == forced_bird]
        cand.sort(key=lambda x: (x.get("featured", 0), x.get("first_seen", "")), reverse=False)
        return forced_bird, next_angle(forced_bird) or "facts", (cand[0] if cand else None)

    best, best_score = None, -1e9
    for x in designs:
        angle = next_angle(x["bird"])
        if not angle:
            continue
        score = 30 if not x.get("featured") else -10 * x.get("featured", 0)
        score += 6 * (x.get("first_seen", "") >= (d - datetime.timedelta(days=14)).isoformat())   # nov dizajn
        score += -6 * len(used[x["bird"]]) + random.uniform(0, 5)
        score += 5 if seasons & set(bird_info(x["bird"])["seasons"]) else 0
        score -= 40 if x["bird"] in recent[:3] else (10 if x["bird"] in recent else 0)
        if score > best_score:
            best, best_score = (x["bird"], angle, x), score
    if best:
        return best

    best, best_score = None, -1e9
    for bird, info in BIRDS.items():
        angle = next_angle(bird)
        if not angle:
            continue
        score = -8 * len(used[bird]) + random.uniform(0, 4)
        score += 7 if in_shop(bird) else 0
        score += 5 if seasons & set(info["seasons"]) else 0
        score += 3 if info["region"] in ("uk", "na", "both") else 0
        score -= 40 if bird in recent[:5] else (12 if bird in recent else 0)
        if score > best_score:
            best, best_score = (bird, angle, None), score
    return best


# ---------------------------------------------------------------------------
# 1) ISTRAŽIVANJE
# ---------------------------------------------------------------------------
def research(bird, angle):
    name = bird_name(bird)
    prompt = f"""You are a careful ornithology researcher. Use Google Search to collect ACCURATE facts about the
{name} ({bird}), as seen in {region_text(bird)}. Prefer: RSPB, BTO, Cornell Lab (All About Birds, Birds of the World),
Audubon, The Wildlife Trusts, BirdLife, IUCN. {SEARCH_HINTS.get(bird, "")}

Write plain text notes with these headings: SCIENTIFIC NAME; SIZE (length, wingspan, weight in metric and imperial);
IDENTIFICATION (adult male, female, juvenile; key field marks); VOICE (song and calls described in words);
RANGE AND SEASONS; HABITAT; DIET; BEHAVIOUR (at least 8 specific facts); BREEDING (nest site, eggs, broods);
LIFESPAN (typical, and the record with its source); CONSERVATION STATUS (IUCN and national lists);
LOOK-ALIKES (and how to tell them apart); GARDEN / BACKYARD TIPS (foods, feeders, water, nest boxes);
SURPRISING FACTS (at least 6); NAMES AND FOLKLORE (origin of the name, old names, cultural links).
Extra detail for this article: {ANGLES[angle]['goal']}

After every fact write the source organisation in brackets, e.g. (RSPB). If something is not certain, write "unknown"
instead of guessing. Numbers must come from a source."""
    try:
        return gemini(prompt, grounded=True, validator=lambda t: len(t) > 900, label="istraživanje")
    except Exception as e:
        print(f"  [!] Istraživanje sa Google pretragom nije uspelo ({redact(e)[:120]}), radim bez pretrage")
        return gemini(prompt + "\nOnly include well-established facts you are sure about.",
                      validator=lambda t: len(t) > 900, label="istraživanje bez pretrage")


# ---------------------------------------------------------------------------
# 2) PISANJE
# ---------------------------------------------------------------------------
def build_write_prompt(bird, angle, notes, posts, feedback, design=None):
    name = bird_name(bird)
    g = garden_word(bird)
    a = ANGLES[angle]
    keyword = a["keyword"].format(bird=bird.lower(), garden=g)
    title_hint = a["title"].format(Name=name, Garden_cap=g.capitalize(), N="N")
    related = [p for p in posts if p["bird"] != bird][:25]
    links_block = "\n".join(f'  post:{p["slug"]} = "{p["title"]}"' for p in related) or "  (no other posts yet)"
    shop_note = ("We sell designs of this exact bird." if in_shop(bird)
                 else "We do not have designs of this exact bird yet, so product links go to the whole shop: talk "
                      "about our funny bird designs in general, not about this species' designs.")
    design_block = ""
    if design:
        design_block = f"""
FEATURED DESIGN (this article is published together with this design from our shop; the reader sees it in the
article): "{design_phrase(design)}" - {design.get('title', '')}
Shoppers' keywords for it: {", ".join(design.get('tags', [])[:15])}
- Mention this design naturally ONCE, in the section where its joke fits best, with the token
  [[design|anchor text]] (e.g. [[design|our "{design_phrase(design)}" {name.lower()} design]]). Explain the joke in
  one sentence only if a fact in the article sets it up. Do not describe the artwork in detail."""
    fb = ""
    if feedback:
        fb = "\n\nYOUR PREVIOUS ATTEMPT HAD THESE PROBLEMS, FIX ALL OF THEM:\n- " + "\n- ".join(feedback)
    return f"""You write for {SITE_NAME} ("{TAGLINE}"), a small independent bird blog and shop of funny bird designs.
Readers: birders and bird lovers in the UK/Europe and North America, many of them new, young birders.
Voice: warm, witty, a little cheeky ("birds with opinions"), but the FACTS come first. Clear British-neutral English
(use "behaviour" or "behavior" consistently; prefer US spelling for North American birds, UK spelling for UK birds).

ARTICLE: about the {name} ({bird}). Angle: {a['goal']}
Main search query to answer: "{keyword}". {SEARCH_HINTS.get(bird, "")}

RESEARCH NOTES (the ONLY source of facts; never add facts, numbers, dates or records that are not in the notes;
skip anything marked unknown):
<<<
{notes[:14000]}
>>>

GOOGLE QUALITY RULES (follow strictly):
- Helpful first: the first two sentences answer the search query directly. Every section gives real, specific
  information a reader can use. No filler, no repeating the same point, no generic intros about "nature lovers".
- Honest: NEVER invent personal experiences ("I saw", "in my garden", "we tested"), quotes, studies, experts,
  prices or product names. Speak as a knowledgeable writer, not as an eyewitness.
- Never use these phrases: {", ".join(BANNED_PHRASES[:24])}.
- Headings: 5-8 H2 sections. Use the questions people actually search as headings where natural
  (e.g. "What does a {name} sound like?"). Optional H3 sub-sections. No heading longer than 70 characters.
- Length: 1100-1600 words in total (intro + sections + FAQ).
- Formatting inside text: **bold** for 3-8 key terms (not whole sentences). Lists via the "bullets" field.

SHOP LINKS (we make our money from these, but they must feel natural and secondary):
- {shop_note}
- Insert 3-5 links in total, using ONLY these tokens: [[stickers|anchor text]], [[tees|anchor text]],
  [[hoodies|anchor text]], [[designs|anchor text]] (all our designs of this bird), [[shop|anchor text]] (whole shop){', [[design|anchor text]] (the featured design, exactly once)' if design else ''}.
- Use at least 2 different token types. Never more than one shop link in a paragraph. No links in the first
  paragraph of the intro. Anchor text 2-6 words, descriptive (e.g. [[stickers|{name.lower()} stickers]]).
- Internal links to our other articles (0-3, only if truly relevant), ONLY with these tokens:
{links_block}
  written as [[post:SLUG|anchor text]].
- Never write raw URLs.{design_block}

Return ONE JSON object with exactly these keys:
- "title": SEO title, 45-62 characters, contains "{name}", matches the search intent, no clickbait, no emojis,
  {'' if angle == 'gifts' else 'no word "gift". '}{title_hint}.
- "meta_description": 135-158 characters, includes "{name}" and a reason to click, no quotes.
- "h1": the on-page headline (can equal the title or be slightly longer, max 80 characters).
- "slug": 3-7 lowercase words joined with hyphens, containing the main keyword (e.g. "{slugify(keyword)}").
- "primary_keyword": "{keyword}".
- "intro": array of 2 paragraphs (plain text with optional **bold**).
- "quick_facts": array of 6-8 objects {{"label": ..., "value": ...}} (e.g. Scientific name, Size, Weight, Lifespan,
  Diet, Where, Conservation status, Best time to see), values short and taken from the notes.
- "sections": array of 5-8 objects {{"heading": ..., "paragraphs": [...], "bullets": [... optional ...],
  "subsections": [{{"heading": ..., "paragraphs": [...]}}] optional}}.
- "faq": array of 3-5 objects {{"q": ..., "a": ...}} with real questions people search, answers 1-3 sentences.
- "sources": array of the organisations from the notes you relied on (e.g. ["RSPB", "BTO"]).
- "image_scene": one sentence for the illustration: the {name} doing something that fits THIS article, in a simple
  natural setting (branch, feeder, reeds...). One bird only, no people, no text, no speech bubbles.
- "image_alt": alt text for the illustration, max 120 characters, starts with "Illustration of".{fb}"""


def plain_text(article):
    parts = list(article.get("intro", []))
    for s in article.get("sections", []):
        parts.append(s.get("heading", ""))
        parts += s.get("paragraphs", []) + s.get("bullets", [])
        for sub in s.get("subsections", []) or []:
            parts.append(sub.get("heading", ""))
            parts += sub.get("paragraphs", [])
    for f in article.get("faq", []):
        parts += [f.get("q", ""), f.get("a", "")]
    return "\n".join(str(p) for p in parts)


def strip_tokens(text):
    return TOKEN_RE.sub(lambda m: m.group(2), text).replace("**", "")


def validate_article(art, bird, angle, posts, design=None):
    issues = []
    if not isinstance(art, dict):
        return ["odgovor nije JSON objekat"]
    for key in ("title", "meta_description", "intro", "quick_facts", "sections", "faq", "image_scene"):
        if not art.get(key):
            issues.append(f'missing "{key}"')
    if issues:
        return issues
    name = bird_name(bird)
    core = name.split()[-1].lower()
    title = str(art["title"]).strip()
    if not (40 <= len(title) <= 66):
        issues.append(f'title is {len(title)} characters, it must be 45-62')
    if core not in title.lower():
        issues.append(f'title must contain "{name}"')
    if angle != "gifts" and re.search(r"(?i)\bgifts?\b", title):
        issues.append('title must not contain the word "gift"')
    md = str(art["meta_description"])
    if not (120 <= len(md) <= 165):
        issues.append(f"meta_description is {len(md)} characters, it must be 135-158")
    if not (5 <= len(art["sections"]) <= 9):
        issues.append(f'{len(art["sections"])} sections, use 5-8')
    heads = [str(s.get("heading", "")).strip() for s in art["sections"]]
    if len(set(h.lower() for h in heads)) != len(heads) or any(not h or len(h) > 80 for h in heads):
        issues.append("every section needs a unique heading of max 70 characters")
    if not (5 <= len(art["quick_facts"]) <= 9):
        issues.append("quick_facts must have 6-8 items")
    if not (3 <= len(art["faq"]) <= 6):
        issues.append("faq must have 3-5 items")
    text = plain_text(art)
    words = len(strip_tokens(text).split())
    if words < 950:
        issues.append(f"the article has only {words} words, write 1100-1600")
    if words > 2100:
        issues.append(f"the article has {words} words, keep it under 1700")
    low = text.lower()
    bad = [p for p in BANNED_PHRASES if p in low]
    if bad:
        issues.append(f"remove these phrases: {', '.join(bad)}")
    if low.count("feathered friend") > 1:
        issues.append('"feathered friend" at most once')
    m = FAKE_EXPERIENCE_RE.search(strip_tokens(text))
    if m:
        issues.append(f'no invented personal experiences ("{m.group(0)}")')
    if re.search(r"https?://|www\.", text):
        issues.append("no raw URLs, only the [[...]] tokens")
    tokens = TOKEN_RE.findall(text)
    product = [t for t, _ in tokens if not t.startswith("post:")]
    n_design = product.count("design")
    if design and n_design == 0:
        issues.append('mention the featured design once with [[design|anchor text]]')
    if n_design > (2 if design else 0):
        issues.append("[[design|...]] may be used only once" if design else "there is no featured design, "
                      "do not use [[design|...]]")
    if not (3 <= len(product) <= 7):
        issues.append(f"use 3-5 shop link tokens (now {len(product)})")
    elif len(set(product)) < 2:
        issues.append("use at least 2 different shop link types")
    slugs = {p["slug"] for p in posts}
    for t, _ in tokens:
        if t.startswith("post:") and t[5:] not in slugs:
            issues.append(f"[[{t}|...]] does not exist, use only the listed posts")
    if "[[" in TOKEN_RE.sub("", text):
        issues.append("broken [[...]] link token; format is [[stickers|anchor text]]")
    intro0 = str(art["intro"][0]) if art["intro"] else ""
    if TOKEN_RE.search(intro0):
        issues.append("no shop links in the first intro paragraph")
    return issues


def write_article(bird, angle, notes, posts, design=None):
    feedback = []
    art = None
    for attempt in range(1, 4):
        prompt = build_write_prompt(bird, angle, notes, posts, feedback, design)
        try:
            art = extract_json(gemini(prompt, json_mode=True, validator=json_ok, label="pisanje"))
        except Exception as e:
            feedback = [f"invalid response: {redact(e)[:100]}"]
            continue
        feedback = validate_article(art, bird, angle, posts, design)
        if not feedback:
            return art
        print(f"  ⟳ Pokušaj {attempt}: {'; '.join(feedback)[:300]}")
    # poslednja šansa: popravi sitnice u kodu
    if art and isinstance(art, dict) and not [f for f in feedback if "missing" in f or "words" in f]:
        print("  ⚠ Objavljujem uz sitne nedostatke koje kod sam popravlja")
        return art
    raise RuntimeError("Gemini nije napisao dovoljno dobar članak: " + "; ".join(feedback)[:300])


# ---------------------------------------------------------------------------
# 3) PROVERA ČINJENICA
# ---------------------------------------------------------------------------
def fact_check(art, bird, notes):
    prompt = f"""You are a strict fact-checker for a bird website. Check the ARTICLE about the {bird_name(bird)} below.
Use Google Search and the RESEARCH NOTES. List ONLY claims that are factually wrong or invented (wrong numbers,
wrong range, wrong behaviour, confused with another species, made-up records, quotes or studies). Ignore style,
jokes, opinions and harmless simplifications.

RESEARCH NOTES:
{notes[:9000]}

ARTICLE:
{strip_tokens(plain_text(art))[:12000]}

Return ONLY JSON: {{"problems": [{{"claim": "exact wrong sentence or part", "fix": "the correct fact"}}]}}
Return {{"problems": []}} if everything is correct."""
    try:
        res = extract_json(gemini(prompt, grounded=True, validator=json_ok, label="provera činjenica"))
    except Exception as e:
        print(f"  [!] Provera sa pretragom nije uspela ({redact(e)[:100]}), proveravam bez pretrage")
        try:
            res = extract_json(gemini(prompt, json_mode=True, validator=json_ok, label="provera činjenica"))
        except Exception as e2:
            print(f"  [!] Provera činjenica nije uspela: {redact(e2)[:100]}")
            return []
    probs = res.get("problems", []) if isinstance(res, dict) else []
    return [p for p in probs if isinstance(p, dict) and p.get("claim")][:12]


def fix_facts(art, bird, angle, problems, posts, design=None):
    fixes = "\n".join(f'- WRONG: "{p.get("claim")}" -> CORRECT: {p.get("fix", "remove it")}' for p in problems)
    prompt = f"""Fix the factual errors in this article JSON. Change ONLY the wrong sentences (rewrite or remove them),
keep everything else, keep all [[...]] link tokens and the same JSON keys. Return the full corrected JSON object.

ERRORS:
{fixes}

ARTICLE JSON:
{json.dumps(art, ensure_ascii=False)}"""
    fixed = extract_json(gemini(prompt, json_mode=True, validator=json_ok, label="ispravka činjenica"))
    issues = validate_article(fixed, bird, angle, posts, design)
    hard = [i for i in issues if "missing" in i or "words" in i or "does not exist" in i]
    if hard:
        raise RuntimeError("ispravljen članak više ne prolazi proveru: " + "; ".join(hard))
    return fixed


# ---------------------------------------------------------------------------
# 4) SLIKA
# ---------------------------------------------------------------------------
def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def hero_prompt(bird, scene):
    info = bird_info(bird)
    prompt = (f"A cute chubby round cartoon {bird_name(bird)} bird with its real markings: {info['marks']}. "
              f"{scene} Flat vector sticker-style illustration, thick dark navy outlines, flat bright colors, simple "
              f"soft natural background in sage green and cream tones, gentle daylight, wide 16:9 composition with "
              f"the bird large and clearly visible, exactly one bird, correct bird anatomy with two wings and two "
              f"legs, no text, no letters, no words, no speech bubble, no watermark, no frame.")
    negative = ("text, letters, words, typography, watermark, logo, signature, speech bubble, frame, border, arms, "
                "hands, human, extra legs, extra wings, two heads, multiple birds, photo, photorealistic, 3d render, "
                "blurry, dark, gloomy")
    return prompt, negative


def check_hero(img_bytes, bird):
    prompt = (f'Look at this illustration. It should show ONE cute cartoon {bird_name(bird)} with these real markings: '
              f'{bird_info(bird)["marks"]}. Return ONLY JSON: {{"species_ok": true/false (false only if a birdwatcher '
              f'would name a different species), "has_text": true/false (any letters, words or numbers anywhere), '
              f'"defect": true/false (arms or hands, extra legs or wings, two heads, more than one bird, a person), '
              f'"note": "short reason"}}')
    try:
        res = extract_json(gemini(prompt, image=(img_bytes, "image/jpeg"), validator=json_ok, label="provera slike"))
    except Exception as e:
        print(f"  [!] Provera slike nije uspela ({redact(e)[:80]}), prihvatam sliku")
        return True, ""
    ok = bool(res.get("species_ok", True)) and not res.get("has_text") and not res.get("defect")
    return ok, str(res.get("note", ""))[:150]


def to_hero_jpeg(raw):
    im = Image.open(BytesIO(raw)).convert("RGB")
    scale = max(IMG_W / im.width, IMG_H / im.height)
    im = im.resize((max(IMG_W, round(im.width * scale)), max(IMG_H, round(im.height * scale))), Image.LANCZOS)
    left, top = (im.width - IMG_W) // 2, (im.height - IMG_H) // 2
    return im.crop((left, top, left + IMG_W, top + IMG_H))


def save_images(im, slug):
    os.makedirs(IMG_DIR, exist_ok=True)
    im.save(os.path.join(IMG_DIR, f"{slug}.jpg"), "JPEG", quality=82, optimize=True, progressive=True)
    thumb = im.resize((600, 338), Image.LANCZOS)
    thumb.save(os.path.join(IMG_DIR, f"{slug}-600.webp"), "WEBP", quality=80)


def make_hero(bird, scene, slug):
    """Vraća True ako je nacrtana nova slika, False ako se koristi podrazumevana."""
    if not FAL_KEY:
        print("  [!] Nema FAL_KEY: članak dobija podrazumevanu sliku")
        return False
    prompt, negative = hero_prompt(bird, scene)
    for attempt in range(1, 4):
        try:
            r = http_request("POST", "https://fal.run/fal-ai/z-image/turbo", headers=fal_headers(),
                             json={"prompt": prompt, "negative_prompt": negative,
                                   "image_size": {"width": 1344, "height": 768}})
            raw = http_request("GET", r.json()["images"][0]["url"]).content
            im = to_hero_jpeg(raw)
            buf = BytesIO()
            im.save(buf, "JPEG", quality=85)
            ok, note = check_hero(buf.getvalue(), bird)
            if ok or attempt == 3:
                if not ok:
                    print(f"  ⚠ Slika ni posle 3 pokušaja nije savršena ({note}), koristim podrazumevanu")
                    return False
                save_images(im, slug)
                return True
            print(f"  ⟳ Slika nije dobra ({note}), pokušaj {attempt + 1}/3")
        except Exception as e:
            print(f"  ✗ Slika, pokušaj {attempt}/3: {redact(e)[:150]}")
            time.sleep(3)
    return False


def fetch_design_image(design):
    """Skida sliku dizajna sa Redbubble CDN-a (prvo veću verziju, pa originalnu)."""
    url = design.get("image_url") or ""
    if not url:
        return None
    cands = []
    bigger = re.sub(r"\d+x\d+-pad,\d+x\d+", "845x845-pad,1000x1000", url)
    if bigger != url:
        cands.append(bigger)
    cands.append(url)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/126.0 Safari/537.36", "Referer": "https://www.redbubble.com/"}
    for c in cands:
        try:
            raw = http_request("GET", c, headers=headers, retries=2, timeout=60).content
            im = Image.open(BytesIO(raw)).convert("RGB")
            if im.width >= 300:
                return im
        except Exception as e:
            print(f"  [!] Slika dizajna nije preuzeta ({redact(e)[:100]})")
    return None


def rounded(size, radius):
    from PIL import ImageDraw
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def design_hero(design_im, slug):
    """Naslovna slika 1200x675: dizajn iz shopa na kartici u bojama brenda (kao kartice na sajtu)."""
    from PIL import ImageDraw
    os.makedirs(IMG_DIR, exist_ok=True)
    full = design_im.copy()
    full.thumbnail((1000, 1000), Image.LANCZOS)
    full.save(os.path.join(IMG_DIR, f"{slug}-design.jpg"), "JPEG", quality=88, optimize=True, progressive=True)
    bg = Image.new("RGB", (IMG_W, IMG_H), (201, 220, 189))
    d = ImageDraw.Draw(bg)
    d.ellipse((IMG_W // 2 - 420, IMG_H // 2 - 420, IMG_W // 2 + 420, IMG_H // 2 + 420), fill=(227, 238, 220))
    side = 560
    x, y = (IMG_W - side) // 2, (IMG_H - side) // 2 - 4
    navy = (27, 34, 54)
    d.rounded_rectangle((x, y + 10, x + side, y + side + 10), radius=36, fill=navy)          # "senka" kao na sajtu
    corner = design_im.getpixel((2, 2))
    card = Image.new("RGB", (side, side), corner)
    inner = design_im.copy()
    inner.thumbnail((side - 40, side - 40), Image.LANCZOS)
    card.paste(inner, ((side - inner.width) // 2, (side - inner.height) // 2))
    bg.paste(card, (x, y), rounded((side, side), 36))
    d.rounded_rectangle((x, y, x + side, y + side), radius=36, outline=navy, width=5)
    save_images(bg, slug)
    return True


# ---------------------------------------------------------------------------
# 5) JEDAN ČLANAK OD POČETKA DO KRAJA
# ---------------------------------------------------------------------------
def unique_slug(base, posts):
    slugs = {p["slug"] for p in posts}
    slug, n = base, 2
    while slug in slugs or os.path.exists(os.path.join(DATA_DIR, slug + ".json")):
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_post(posts, shop=None):
    d = today()
    topic = pick_topic(posts, d, shop)
    if not topic:
        raise RuntimeError("Sve ptice su obrađene u svim uglovima: dodaj nove ptice u birds_data.py")
    bird, angle, design = topic
    print(f"\n=== {bird_name(bird)} / {angle} / dizajn: {design['title'] if design else '-'} ===")
    t0 = time.time()
    notes = research(bird, angle)
    print(f"  ✓ istraživanje ({len(notes)} znakova)")
    art = write_article(bird, angle, notes, posts, design)
    print(f"  ✓ članak: {art['title']}")
    problems = fact_check(art, bird, notes)
    if problems:
        print(f"  ⟳ provera našla {len(problems)} grešaka, ispravljam")
        art = fix_facts(art, bird, angle, problems, posts, design)
        left = fact_check(art, bird, notes)
        if len(left) > 2:
            raise RuntimeError(f"posle ispravke i dalje {len(left)} netačnih tvrdnji, ne objavljujem: "
                               + "; ".join(p['claim'][:60] for p in left))
        print(f"  ✓ ispravljeno (preostalo sitnih: {len(left)})")
    else:
        print("  ✓ provera činjenica: bez grešaka")
    slug = unique_slug(slugify(art.get("slug") or art["title"], 60), posts)
    has_img, design_img = False, ""
    if design:
        im = fetch_design_image(design)
        if im is not None:
            has_img = design_hero(im, slug)
            design_img = f"/blog/images/{slug}-design.jpg"
    if not has_img:
        has_img = make_hero(bird, str(art.get("image_scene", "")), slug)
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat() + "Z"
    post = {
        "slug": slug, "bird": bird, "angle": angle, "date": now, "updated": now,
        "title": clean_line(art["title"], 70), "h1": clean_line(art.get("h1") or art["title"], 90),
        "meta_description": clean_line(art["meta_description"], 165),
        "primary_keyword": clean_line(art.get("primary_keyword", ""), 80),
        "intro": art["intro"], "quick_facts": art["quick_facts"], "sections": art["sections"], "faq": art["faq"],
        "sources": art.get("sources", []), "image": f"/blog/images/{slug}.jpg" if has_img else "",
        "image_alt": clean_line(art.get("image_alt") or f"Illustration of a {bird_name(bird)}", 125),
        "words": len(strip_tokens(plain_text(art)).split()),
    }
    if design:
        post["design"] = {"id": design.get("id"), "title": design.get("title"), "phrase": design_phrase(design),
                          "url": design.get("url"), "product_type": design.get("product_type", ""),
                          "image": design_img or design.get("image_url", "")}
        if design_img:
            post["image_alt"] = clean_line(f'\u201c{design_phrase(design)}\u201d {bird_name(bird)} design by {SITE_NAME}', 125)
        design["featured"] = int(design.get("featured", 0)) + 1
        if shop is not None:
            save_shop(shop)
    save_post(post)
    print(f"  ✓ objavljeno za {time.time() - t0:.0f} s: {absu(post_path(post))}")
    return post


def clean_line(text, limit):
    t = re.sub(r"\s+", " ", strip_tokens(str(text))).strip().strip('"')
    return t[:limit].rstrip()


# ---------------------------------------------------------------------------
# 6) HTML
# ---------------------------------------------------------------------------
def post_path(p):
    return f"/blog/{p['slug']}.html"


def hub_path(bird):
    return f"/birds/{bird_slug(bird)}.html"


def post_image(p, size="full"):
    if p.get("image"):
        if size == "thumb":
            return u(p["image"].replace(".jpg", "-600.webp"))
        return u(p["image"])
    return u("/assets/og-default.jpg")


def render_inline(text, bird, posts_by_slug, design=None):
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)

    def link(m):
        kind, anchor = m.group(1), m.group(2)
        if kind.startswith("post:"):
            target = posts_by_slug.get(kind[5:])
            if not target:
                return anchor
            return f'<a href="{u(post_path(target))}">{anchor}</a>'
        return f'<a href="{esc(rb_link(kind, bird, design))}" target="_blank" rel="noopener">{anchor}</a>'

    # tokeni su posle esc() i dalje čitljivi jer [, ], | i slova nisu escapovani
    return TOKEN_RE.sub(link, t)


def head(title, description, path, image=None, og_type="website", extra="", noindex=False, image_alt=""):
    canonical = absu(path)
    img = image or absu("/assets/og-default.jpg")
    verify = ""
    if CONFIG.get("google_site_verification"):
        verify += f'<meta name="google-site-verification" content="{esc(CONFIG["google_site_verification"])}">\n'
    if CONFIG.get("pinterest_verification"):
        verify += f'<meta name="p:domain_verify" content="{esc(CONFIG["pinterest_verification"])}">\n'
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large, max-snippet:-1"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="robots" content="{robots}">
{verify}<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(img)}">
<meta property="og:image:alt" content="{esc(image_alt or title)}">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(img)}">
<meta name="theme-color" content="#c9dcbd">
<link rel="icon" href="{u('/assets/favicon.ico')}" sizes="32x32">
<link rel="icon" href="{u('/assets/logo-192.png')}" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="{u('/assets/apple-touch-icon.png')}">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE_NAME)}" href="{u('/feed.xml')}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600&family=Nunito:wght@400;700;800&display=swap">
<link rel="stylesheet" href="{u('/assets/style.css')}?v={ASSET_VERSION}">
{extra}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{promo_html()}<header class="site-header">
 <div class="wrap">
  <a class="brand" href="{u('/')}"><img src="{u('/assets/logo.png')}" width="46" height="46" alt="{esc(SITE_NAME)} logo">
   <span class="brand-name">Feathered <span>Gossip</span></span></a>
  <nav class="nav" aria-label="Main">
   <a href="{u('/blog.html')}">Blog</a>
   <a href="{u('/birds.html')}">Birds</a>
   <a href="{u('/about.html')}">About</a>
   <a class="btn small" href="{esc(SHOP_URL)}" target="_blank" rel="noopener">Shop</a>
  </nav>
 </div>
</header>
<main id="main">
"""


def promo_html():
    text = CONFIG.get("promo_text", "").strip()
    if not text:
        return ""
    return (f'<div class="promo">{esc(text)} <a href="{esc(SHOP_URL)}" target="_blank" rel="noopener">'
            f'Shop now</a></div>\n')


def foot():
    year = today().year
    return f"""</main>
<footer class="site-footer">
 <div class="wrap">
  <div>
   <div class="brand-name">Feathered <span>Gossip</span></div>
   <p>{esc(TAGLINE)} Fact-checked bird articles and funny bird designs for people who stop mid-sentence for a bird.</p>
   <p class="note">&copy; {year} {esc(SITE_NAME)}. Our designs are sold on Redbubble.</p>
  </div>
  <nav class="foot-links" aria-label="Footer">
   <a href="{u('/blog.html')}">Blog</a>
   <a href="{u('/birds.html')}">Birds</a>
   <a href="{u('/about.html')}">About</a>
   <a href="{u('/privacy.html')}">Privacy</a>
   <a href="{esc(SHOP_URL)}" target="_blank" rel="noopener">Redbubble shop</a>
   <a href="{u('/feed.xml')}">RSS</a>
  </nav>
 </div>
</footer>
</body>
</html>
"""


def jsonld(obj):
    return ('<script type="application/ld+json">' +
            json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n")


def org_ld():
    return {"@type": "Organization", "@id": absu("/#org"), "name": SITE_NAME, "url": absu("/"),
            "logo": {"@type": "ImageObject", "url": absu("/assets/logo-512.png"), "width": 512, "height": 512},
            "sameAs": [SHOP_URL] + [v for v in CONFIG.get("social", {}).values() if v]}


def card(p, lazy=True):
    loading = ' loading="lazy" decoding="async"' if lazy else ""
    return f"""<article class="card">
 <a class="cover" href="{u(post_path(p))}" tabindex="-1" aria-hidden="true"><img src="{post_image(p, 'thumb')}" width="600" height="338" alt=""{loading}></a>
 <div class="body">
  <h3><a href="{u(post_path(p))}">{esc(p['title'])}</a></h3>
  <p>{esc(p['meta_description'])}</p>
  <div class="meta">{esc(bird_name(p['bird']))} &middot; {nice_date(p['date'])}</div>
 </div>
</article>"""


def shop_box(bird, heading_tag="h2"):
    name = bird_name(bird)
    if in_shop(bird):
        title = f"Birds with opinions: {name} edition"
        text = (f"Funny {name} designs from our shop, for people who stop mid-sentence for a bird. "
                f"Printed on demand by Redbubble.")
        links = [("stickers", f"{name} stickers"), ("tees", f"{name} T-shirts"), ("hoodies", f"{name} hoodies"),
                 ("designs", "All designs")]
    else:
        title = "Birds with opinions, on stickers and tees"
        text = "Funny bird designs for birders and bird nerds, printed on demand by Redbubble."
        links = [("stickers", "Bird stickers"), ("tees", "Bird T-shirts"), ("hoodies", "Bird hoodies"),
                 ("shop", "Whole shop")]
    btns = "".join(f'<a class="btn small" href="{esc(rb_link(k, bird))}" target="_blank" rel="noopener">{esc(t)}</a>'
                   for k, t in links)
    return (f'<aside class="shopbox" aria-label="Shop"><{heading_tag}>{esc(title)}</{heading_tag}>'
            f'<p>{esc(text)}</p><div class="links">{btns}</div></aside>\n')


def anchor_id(text, used):
    base = slugify(text, 50)
    aid, n = base, 2
    while aid in used:
        aid, n = f"{base}-{n}", n + 1
    used.add(aid)
    return aid


def sources_html(names):
    seen, out = set(), []
    for n in names or []:
        low = str(n).lower()
        for key, (label, url) in TRUSTED_SOURCES.items():
            if key in low and label not in seen:
                seen.add(label)
                out.append(f'<a href="{url}" rel="noopener" target="_blank">{esc(label)}</a>')
    if not out:
        return ""
    return ('<p class="sources"><strong>Sources:</strong> ' + ", ".join(out) +
            '. Facts were gathered from these organisations, and every article is fact-checked against them '
            f'before publishing. Spotted a mistake? <a href="{u("/about.html")}#contact">Tell us</a>.</p>\n')


def related_posts(p, posts, n=3):
    others = [q for q in posts if q["slug"] != p["slug"]]
    region = bird_info(p["bird"])["region"]
    same = [q for q in others if q["bird"] == p["bird"]]
    near = [q for q in others if q["bird"] != p["bird"] and bird_info(q["bird"])["region"] == region]
    rest = [q for q in others if q not in same and q not in near]
    return (same + near + rest)[:n]


def hero_link_open(p):
    dz = p.get("design")
    if not dz:
        return ""
    return f'<a href="{esc(dz.get("url") or design_link(dz, "all"))}" target="_blank" rel="noopener">'


def design_box(p):
    dz = p["design"]
    bird = p["bird"]
    img = dz.get("image") or ""
    src = u(img) if img.startswith("/") else img
    btns = [("stickers", "Sticker"), ("tees", "T-shirt"), ("hoodies", "Hoodie"), ("all", "All products")]
    links = "".join(f'<a class="btn small" href="{esc(design_link(dz, k))}" target="_blank" rel="noopener">{t}</a>'
                    for k, t in btns)
    pic = (f'<a href="{esc(dz.get("url") or design_link(dz, "all"))}" target="_blank" rel="noopener">'
           f'<img src="{esc(src)}" width="220" height="220" alt="{esc(dz.get("phrase", ""))} {esc(bird_name(bird))} design" '
           f'loading="lazy" decoding="async"></a>') if src else ""
    return (f'<aside class="shopbox design-box" aria-label="Featured design">{pic}<div>'
            f'<h3>The design behind this article: &ldquo;{esc(dz.get("phrase", ""))}&rdquo;</h3>'
            f'<p>Our {esc(bird_name(bird))} design from the {esc(SITE_NAME)} shop, printed on demand by '
            f'Redbubble on stickers, T-shirts, hoodies and more.</p><div class="links">{links}</div></div></aside>\n')


def render_post(p, posts, posts_by_slug):
    bird = p["bird"]
    dz = p.get("design")
    name = bird_name(bird)
    url = absu(post_path(p))
    img_abs = absu(p["image"]) if p.get("image") else absu("/assets/og-default.jpg")
    words = p.get("words") or len(strip_tokens(plain_text(p)).split())
    minutes = max(1, math.ceil(words / 220))
    used_ids = set()
    toc_items, body = [], []
    for i, s in enumerate(p["sections"]):
        aid = anchor_id(s.get("heading", ""), used_ids)
        toc_items.append(f'<li><a href="#{aid}">{esc(strip_tokens(s.get("heading", "")))}</a></li>')
        body.append(f'<h2 id="{aid}">{esc(strip_tokens(s.get("heading", "")))}</h2>')
        for para in s.get("paragraphs", []):
            body.append(f"<p>{render_inline(para, bird, posts_by_slug, dz)}</p>")
        if s.get("bullets"):
            body.append("<ul>" + "".join(f"<li>{render_inline(b, bird, posts_by_slug, dz)}</li>" for b in s["bullets"])
                        + "</ul>")
        for sub in s.get("subsections", []) or []:
            body.append(f'<h3>{esc(strip_tokens(sub.get("heading", "")))}</h3>')
            for para in sub.get("paragraphs", []):
                body.append(f"<p>{render_inline(para, bird, posts_by_slug, dz)}</p>")
        if i == 2 and len(p["sections"]) > 4:
            body.append(design_box(p) if dz else shop_box(bird, "h3"))
    facts = "".join(f"<dt>{esc(strip_tokens(f.get('label', '')))}</dt><dd>{esc(strip_tokens(f.get('value', '')))}</dd>"
                    for f in p["quick_facts"] if isinstance(f, dict))
    faq = "".join(f"<h3>{esc(strip_tokens(f.get('q', '')))}</h3><p>{render_inline(f.get('a', ''), bird, posts_by_slug, dz)}</p>"
                  for f in p["faq"] if isinstance(f, dict))
    rel = related_posts(p, posts)
    rel_html = ""
    if rel:
        rel_html = ('<section class="block"><div class="wrap"><div class="section-head"><h2>Keep reading</h2>'
                    f'<a href="{u(hub_path(bird))}">More about the {esc(name)} &rarr;</a></div>'
                    '<div class="grid">' + "".join(card(q) for q in rel) + "</div></div></section>\n")
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BlogPosting", "@id": url + "#article", "headline": p["title"][:110],
             "description": p["meta_description"], "image": [img_abs], "datePublished": p["date"],
             "dateModified": p.get("updated", p["date"]), "inLanguage": "en", "mainEntityOfPage": url,
             "wordCount": words, "keywords": p.get("primary_keyword", ""), "about": {"@type": "Thing", "name": name},
             "author": {"@type": "Organization", "name": SITE_NAME, "url": absu("/about.html")},
             "publisher": {"@id": absu("/#org")}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": absu("/")},
                {"@type": "ListItem", "position": 2, "name": "Blog", "item": absu("/blog.html")},
                {"@type": "ListItem", "position": 3, "name": name, "item": absu(hub_path(bird))},
                {"@type": "ListItem", "position": 4, "name": p["title"], "item": url}]},
            org_ld(),
        ]}
    extra = (f'<meta property="article:published_time" content="{p["date"]}">\n'
             f'<meta property="article:modified_time" content="{p.get("updated", p["date"])}">\n'
             f'<meta property="article:section" content="{esc(name)}">\n'
             f'<link rel="preload" as="image" href="{post_image(p)}" fetchpriority="high">\n' + jsonld(ld))
    updated = ""
    if p.get("updated", p["date"])[:10] != p["date"][:10]:
        updated = f' &middot; Updated <time datetime="{p["updated"]}">{nice_date(p["updated"])}</time>'
    page_title = p["title"] if len(p["title"]) + len(SITE_NAME) + 3 > 65 else f'{p["title"]} | {SITE_NAME}'
    out = [head(page_title, p["meta_description"], post_path(p), img_abs, "article", extra,
                image_alt=p.get("image_alt", "")),
           f"""<article class="article">
<nav class="crumbs" aria-label="Breadcrumb"><a href="{u('/')}">Home</a> &rsaquo; <a href="{u('/blog.html')}">Blog</a> &rsaquo; <a href="{u(hub_path(bird))}">{esc(name)}</a></nav>
<h1>{esc(p.get('h1') or p['title'])}</h1>
<div class="byline">By <a href="{u('/about.html')}">{esc(SITE_NAME)}</a> &middot; <time datetime="{p['date']}">{nice_date(p['date'])}</time>{updated} &middot; {minutes} min read</div>
<figure>{hero_link_open(p)}<img class="hero-img" src="{post_image(p)}" width="{IMG_W}" height="{IMG_H}" alt="{esc(p.get('image_alt', ''))}" fetchpriority="high">{'</a>' if dz else ''}
<figcaption>{esc(p.get('image_alt', ''))}</figcaption></figure>
"""]
    out += [f"<p>{render_inline(x, bird, posts_by_slug, dz)}</p>" for x in p["intro"]]
    out.append(f'<div class="facts"><h2>{esc(name)} at a glance</h2><dl>{facts}</dl></div>')
    if len(toc_items) >= 4:
        out.append('<nav class="toc" aria-label="In this article"><strong>In this article</strong><ol>'
                   + "".join(toc_items) + "</ol></nav>")
    out += body
    if faq:
        out.append(f'<section class="faq"><h2 id="faq">Frequently asked questions</h2>{faq}</section>')
    out.append(shop_box(bird))
    out.append(sources_html(p.get("sources")))
    out.append("</article>\n")
    out.append(rel_html)
    out.append(foot())
    return "\n".join(out)


def render_index(posts):
    latest = posts[:9]
    cols = [("stickers", "Stickers", "Laptop, water bottle and field-guide stickers with very opinionated birds.",
             "col-stickers.webp", "Shop stickers"),
            ("tees", "T-shirts", "Classic, relaxed and fitted tees for birders who need everyone to know.",
             "col-tees.webp", "Shop T-shirts"),
            ("hoodies", "Hoodies", "Cosy hoodies for dawn chorus walks and cold hides.", "col-hoodies.webp",
             "Shop hoodies"),
            ("shop", "Everything else", "Mugs, tote bags, notebooks, phone cases and 80+ more products.",
             "col-all.webp", "Visit the shop")]
    col_html = "".join(f"""<article class="card"><a class="cover" href="{esc(rb_link(k))}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true"><img src="{u('/assets/' + img)}" width="560" height="560" alt="" loading="lazy" decoding="async"></a>
<div class="body"><h3><a href="{esc(rb_link(k))}" target="_blank" rel="noopener">{esc(t)}</a></h3><p>{esc(d)}</p><a class="btn small" href="{esc(rb_link(k))}" target="_blank" rel="noopener">{esc(b)}</a></div></article>"""
                       for k, t, d, img, b in cols)
    posts_html = "".join(card(p, lazy=i > 2) for i, p in enumerate(latest)) or \
        '<p>The first article is on its way. Check back tomorrow!</p>'
    chips = bird_chips(posts)
    desc = ("Fun, fact-checked articles about garden and backyard birds, plus funny bird stickers, T-shirts and "
            "hoodies for birders. Birds with opinions.")
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": absu("/#site"), "name": SITE_NAME, "url": absu("/"), "description": desc,
         "publisher": {"@id": absu("/#org")}, "inLanguage": "en"}, org_ld()]}
    return (head(f"{SITE_NAME}: Bird Facts, Birding Humor & Bird Gifts", desc, "/", extra=jsonld(ld)) + f"""
<section class="hero">
 <div class="wrap">
  <div>
   <h1>Bird facts, birding humor and birds with opinions</h1>
   <p class="lead">{esc(SITE_NAME)} is a little corner of the internet for people who stop mid-sentence for a bird:
   fact-checked guides to the birds in your garden and backyard, and funny bird designs to wear about it.</p>
   <div class="cta"><a class="btn blue" href="{u('/blog.html')}">Read the blog</a>
   <a class="btn" href="{esc(SHOP_URL)}" target="_blank" rel="noopener">Visit the shop</a></div>
  </div>
  <img src="{u('/assets/hero-birds.webp')}" width="900" height="446" alt="Cartoon blue tit, robin and wren gossiping on a branch" fetchpriority="high">
 </div>
</section>
<section class="block"><div class="wrap">
 <div class="section-head"><h2>Latest from the blog</h2><a href="{u('/blog.html')}">See all articles &rarr;</a></div>
 <div class="grid">{posts_html}</div>
</div></section>
<section class="block collections"><div class="wrap">
 <div class="section-head"><h2>Shop the collections</h2><a href="{esc(SHOP_URL)}" target="_blank" rel="noopener">All designs on Redbubble &rarr;</a></div>
 <div class="grid">{col_html}</div>
</div></section>
{f'<section class="block"><div class="wrap"><h2>Browse by bird</h2>{chips}</div></section>' if chips else ''}
<section class="block"><div class="wrap page" style="padding:0">
 <h2>Who is behind Feathered Gossip?</h2>
 <p>We are a small independent bird-design shop. Our articles are researched from trusted birding sources such as
 the RSPB, BTO and the Cornell Lab of Ornithology, and every one is fact-checked before it goes live.
 <a href="{u('/about.html')}">Read how we write our articles</a>.</p>
</div></section>
""" + foot())


def bird_chips(posts):
    birds = Counter(p["bird"] for p in posts)
    if not birds:
        return ""
    return '<div class="chips">' + "".join(
        f'<a class="chip" href="{u(hub_path(b))}">{esc(bird_name(b))} ({n})</a>'
        for b, n in sorted(birds.items(), key=lambda x: bird_name(x[0]))) + "</div>"


def render_blog(posts):
    desc = "All Feathered Gossip articles: bird identification guides, surprising bird facts, garden and backyard " \
           "bird tips, and gift ideas for bird lovers."
    cards = "".join(card(p, lazy=i > 5) for i, p in enumerate(posts)) or "<p>The first article is on its way.</p>"
    ld = {"@context": "https://schema.org", "@type": "Blog", "name": f"{SITE_NAME} blog", "url": absu("/blog.html"),
          "publisher": org_ld(), "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": absu(post_path(p)),
                                               "datePublished": p["date"]} for p in posts[:30]]}
    return (head(f"Bird Blog: Facts, ID Guides and Garden Tips | {SITE_NAME}", desc, "/blog.html", extra=jsonld(ld))
            + f"""<section class="block"><div class="wrap">
<h1>The Feathered Gossip blog</h1>
<p class="lead">Fact-checked bird articles with a sense of humour: how to identify birds, why they do the odd things
they do, how to bring them to your garden or backyard, and the occasional gift guide.</p>
{bird_chips(posts)}
<div class="grid" style="margin-top:26px">{cards}</div>
</div></section>
""" + foot())


def render_hub(bird, bposts):
    name = bird_name(bird)
    info = bird_info(bird)
    desc = (f"Everything about the {name} on {SITE_NAME}: identification, facts, behaviour and "
            f"{garden_word(bird)} tips, plus funny {name.lower()} designs.")[:160]
    cards = "".join(card(p) for p in bposts)
    noindex = len(bposts) < 2       # tanka stranica sa jednim člankom se ne nudi Google-u
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{name} articles",
          "url": absu(hub_path(bird)), "about": {"@type": "Thing", "name": name}}
    return (head(f"{name}: Facts, ID Tips and Articles | {SITE_NAME}", desc, hub_path(bird), extra=jsonld(ld),
                 noindex=noindex) + f"""<section class="block"><div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="{u('/')}">Home</a> &rsaquo; <a href="{u('/birds.html')}">Birds</a> &rsaquo; {esc(name)}</nav>
<h1>{esc(name)}</h1>
<p class="lead">All our articles about the {esc(name)}, a bird of {esc(region_text(bird))}. Look out for: {esc(info['marks'])}.</p>
<div class="grid" style="margin-top:22px">{cards}</div>
<div class="page" style="padding:0">{shop_box(bird)}</div>
</div></section>
""" + foot()), noindex


def render_birds(posts):
    by_region = defaultdict(list)
    counts = Counter(p["bird"] for p in posts)
    for b in counts:
        by_region[bird_info(b)["region"]].append(b)
    labels = [("uk", "Garden birds of Britain and Europe"), ("na", "Backyard birds of North America"),
              ("both", "Birds of both sides of the Atlantic"), ("world", "Birders' favourites from around the world")]
    blocks = ""
    for key, label in labels:
        if by_region.get(key):
            chips = "".join(f'<a class="chip" href="{u(hub_path(b))}">{esc(bird_name(b))} ({counts[b]})</a>'
                            for b in sorted(by_region[key], key=bird_name))
            blocks += f'<h2>{esc(label)}</h2><div class="chips">{chips}</div>'
    desc = "Browse Feathered Gossip articles by bird species: garden birds of Britain and Europe, backyard birds of " \
           "North America and birders' favourites."
    return head(f"Birds A-Z | {SITE_NAME}", desc, "/birds.html") + f"""<section class="block"><div class="wrap">
<h1>Birds A-Z</h1>
<p class="lead">Pick a bird and read everything we have written about it.</p>
{blocks or '<p>The first article is on its way.</p>'}
</div></section>
""" + foot()


def render_about():
    contact = CONFIG.get("contact_email", "").strip()
    contact_html = (f'Email us at <a href="mailto:{esc(contact)}">{esc(contact)}</a>.' if contact else
                    f'Send us a message through our <a href="{esc(SHOP_URL)}" target="_blank" rel="noopener">'
                    f'Redbubble shop</a>.')
    desc = f"About {SITE_NAME}: who we are, how our bird articles are researched and fact-checked, and where our designs are sold."
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "name": f"About {SITE_NAME}", "url": absu("/about.html"),
          "mainEntity": org_ld()}
    return head(f"About Us | {SITE_NAME}", desc, "/about.html", extra=jsonld(ld)) + f"""<div class="page">
<h1>About {esc(SITE_NAME)}</h1>
<p><strong>{esc(TAGLINE)}</strong> {esc(SITE_NAME)} is a small, independent shop of funny bird designs and a blog
for people who love birds, from brand-new backyard birders to people with a well-worn field guide.</p>
<h2>What we write about</h2>
<p>We write about the birds people actually see: garden birds of Britain and Europe, backyard birds of North America
and a few birders' favourites from further away. You will find identification guides, surprising facts, the science
behind odd bird behaviour, tips for making your garden or backyard bird-friendly, and the occasional gift guide.</p>
<h2>How our articles are made</h2>
<p>Every article starts with research from trusted ornithology sources such as the RSPB, the BTO, the Cornell Lab of
Ornithology, the National Audubon Society and BirdLife International. We draft articles with the help of AI writing
tools, using only the researched facts, and then run a separate fact-check against those sources before anything
is published. Each article lists the organisations it is based on.</p>
<p>We are bird lovers, not a scientific institution. If you spot a mistake, we really want to know and we will fix
it quickly.</p>
<h2>Our designs</h2>
<p>Our bird designs are sold through <a href="{esc(SHOP_URL)}" target="_blank" rel="noopener">our shop on
Redbubble</a>, which prints and ships every order. When an article mentions our stickers, T-shirts or hoodies, the
link goes to our own shop. We do not take money from anyone else for mentions or links.</p>
<h2 id="contact">Contact</h2>
<p>{contact_html}</p>
</div>
""" + foot()


def render_privacy():
    desc = f"Privacy policy for {SITE_NAME}."
    return head(f"Privacy Policy | {SITE_NAME}", desc, "/privacy.html") + f"""<div class="page">
<h1>Privacy policy</h1>
<p>Last updated: {nice_date(today().isoformat())}</p>
<p>This website is a static blog. We do not ask you to create an account, we do not run ads, and we do not set
our own cookies or use analytics or tracking scripts.</p>
<h2>Hosting</h2>
<p>The site is hosted on GitHub Pages. Like any web host, GitHub may log technical information such as your IP
address when you visit, for security and operational purposes. See the
<a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" target="_blank" rel="noopener">GitHub Privacy Statement</a>.</p>
<h2>Fonts</h2>
<p>Text fonts are loaded from Google Fonts, which receives your IP address when the font files are downloaded. See
the <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google Privacy Policy</a>.</p>
<h2>Shop links</h2>
<p>Links to our shop take you to Redbubble, which has its own privacy policy and handles all orders and payments.</p>
<h2>Contact</h2>
<p>Questions about this policy? See the <a href="{u('/about.html')}#contact">contact details on our About page</a>.</p>
</div>
""" + foot()


def render_404():
    return head(f"Page not found | {SITE_NAME}", "This page flew away.", "/404.html", noindex=True) + f"""<div class="page">
<h1>This page flew the nest</h1>
<p>The page you were looking for does not exist anymore, or it migrated somewhere else.</p>
<p><a class="btn blue" href="{u('/')}">Back to the home page</a> <a class="btn" href="{u('/blog.html')}">Read the blog</a></p>
</div>
""" + foot()


def render_sitemap(posts, hub_index):
    def url(loc, lastmod, prio):
        return f"<url><loc>{esc(absu(loc))}</loc><lastmod>{lastmod[:10]}</lastmod><priority>{prio}</priority></url>"
    newest = posts[0]["updated"] if posts else today().isoformat()
    items = [url("/", newest, "1.0"), url("/blog.html", newest, "0.8"), url("/birds.html", newest, "0.6"),
             url("/about.html", newest, "0.4"), url("/privacy.html", newest, "0.2")]
    items += [url(post_path(p), p.get("updated", p["date"]), "0.9") for p in posts]
    items += [url(hub_path(b), last, "0.6") for b, last in hub_index]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(items) + "\n</urlset>\n")


def render_feed(posts):
    def rfc822(iso):
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for p in posts[:30]:
        img = absu(p["image"]) if p.get("image") else absu("/assets/og-default.jpg")
        items.append(f"""<item>
 <title>{esc(p['title'])}</title>
 <link>{esc(absu(post_path(p)))}</link>
 <guid isPermaLink="true">{esc(absu(post_path(p)))}</guid>
 <pubDate>{rfc822(p['date'])}</pubDate>
 <description>{esc(p['meta_description'])}</description>
 <category>{esc(bird_name(p['bird']))}</category>
 <enclosure url="{esc(img)}" type="image/jpeg" length="0"/>
 <media:content url="{esc(img)}" medium="image" type="image/jpeg" width="{IMG_W}" height="{IMG_H}"/>
</item>""")
    last = rfc822(posts[0]["date"]) if posts else rfc822(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{esc(SITE_NAME)}</title>
<link>{esc(absu('/'))}</link>
<atom:link href="{esc(absu('/feed.xml'))}" rel="self" type="application/rss+xml"/>
<description>{esc(TAGLINE)} Fact-checked bird articles and birding humor.</description>
<language>en</language>
<lastBuildDate>{last}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


ASSET_VERSION = "1"


def write(path, content):
    full = os.path.join(SITE_DIR, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def build_site():
    global ASSET_VERSION
    posts = load_posts()
    os.makedirs(SITE_DIR, exist_ok=True)
    dst = os.path.join(SITE_DIR, "assets")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(ASSETS_SRC, dst)
    try:
        ASSET_VERSION = str(int(os.path.getmtime(os.path.join(ASSETS_SRC, "style.css"))))
    except OSError:
        pass
    # članci koji su obrisani iz data/ nestaju i sa sajta
    blog_dir = os.path.join(SITE_DIR, "blog")
    keep = {p["slug"] + ".html" for p in posts}
    if os.path.isdir(blog_dir):
        for name in os.listdir(blog_dir):
            if name.endswith(".html") and name not in keep:
                os.remove(os.path.join(blog_dir, name))
    birds_dir = os.path.join(SITE_DIR, "birds")
    if os.path.isdir(birds_dir):
        shutil.rmtree(birds_dir)
    by_slug = {p["slug"]: p for p in posts}
    for p in posts:
        write(post_path(p), render_post(p, posts, by_slug))
    by_bird = defaultdict(list)
    for p in posts:
        by_bird[p["bird"]].append(p)
    hub_index = []
    for bird, bposts in by_bird.items():
        page, noindex = render_hub(bird, bposts)
        write(hub_path(bird), page)
        if not noindex:
            hub_index.append((bird, bposts[0].get("updated", bposts[0]["date"])))
    write("/index.html", render_index(posts))
    write("/blog.html", render_blog(posts))
    write("/birds.html", render_birds(posts))
    write("/about.html", render_about())
    write("/privacy.html", render_privacy())
    write("/404.html", render_404())
    write("/sitemap.xml", render_sitemap(posts, hub_index))
    write("/feed.xml", render_feed(posts))
    write("/robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {absu('/sitemap.xml')}\n")
    write("/.nojekyll", "")
    print(f"✓ Sajt izgrađen: {len(posts)} članaka, {len(by_bird)} ptica -> {SITE_DIR}")
    return posts


# ---------------------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------------------
def tg(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]}, timeout=30)
    except Exception as e:
        print(f"Telegram poruka nije poslata: {redact(e)[:120]}")


def main():
    if "--rebuild" in sys.argv or os.getenv("REBUILD_ONLY") == "1":
        sync_shop_birds(load_shop())
        build_site()
        return
    if genai is None:
        raise SystemExit("Instaliraj zavisnosti: pip install -r requirements.txt")
    posts = load_posts()
    shop = refresh_shop(force=os.getenv("SHOP_REFRESH") == "1")
    sync_shop_birds(shop)
    made, failed = [], []
    for i in range(POSTS_PER_RUN):
        try:
            post = create_post(posts, shop)
            posts.insert(0, post)
            made.append(post)
        except Exception as e:
            print(f"✗ Članak nije napravljen: {redact(e)[:300]}")
            failed.append(redact(e)[:200])
    build_site()
    for p in made:
        tg(f"🐦 Novi članak na {SITE_NAME}:\n{p['title']}\n{absu(post_path(p))}")
    if failed:
        tg(f"⚠ {SITE_NAME}: članak nije napravljen danas.\n" + "\n".join(failed))
    if POSTS_PER_RUN and not made:
        sys.exit(1)


if __name__ == "__main__":
    main()

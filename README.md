# Feathered Gossip blog

Sajt **Feathered Gossip** (Birds with opinions.) koji svaki dan sam objavi jedan SEO članak o ptici iz tvog Redbubble shopa,
sa slikom dizajna i linkovima ka nalepnicama, majicama, duksevima i celom shopu.

## Kako radi

1. **Jednom nedeljno** bot preko Apify-ja pročita tvoj Redbubble shop (`WolfBeat-Shop`): nazive dizajna, tagove, slike i
   linkove. Sam prepozna koja je ptica na svakom dizajnu.
2. **Svaki dan** izabere dizajn koji još nije imao članak (noviji dizajni prvo) i ugao članka za tu pticu:
   prepoznavanje, zanimljive činjenice, dvorište, ponašanje, pesma, slične vrste, gnežđenje, folklor, pokloni.
3. Gemini sa **Google pretragom** skupi činjenice (RSPB, BTO, Cornell Lab, Audubon...), napiše članak samo iz njih, a
   drugi Gemini poziv **proveri činjenice** i ispravi greške pre objave.
4. Naslovna slika je **tvoj dizajn** u bojama brenda (1200x675, dovoljno veliko za Google Discover).
5. U članku: linkovi ka tom dizajnu (nalepnica, majica, duks, svi proizvodi), ka svim dizajnima te ptice i ka shopu.
6. Ceo sajt se ponovo izgradi (početna, blog, stranice ptica, `sitemap.xml`, `feed.xml`) i objavi na GitHub Pages.

SEO je ugrađen: jedinstveni naslovi i opisi, canonical, Open Graph, `max-image-preview:large`, schema.org
(BlogPosting, Breadcrumb, Organization), sitemap, RSS, interni linkovi, brzo učitavanje, mobilni prikaz, stranica
„About“ koja objašnjava kako se članci prave i proveravaju. Bot piše najviše 1 članak dnevno, jer Google kažnjava
masovno pravljene stranice.

## Postavljanje (jednom, oko 20 minuta)

### 1. GitHub nalog i repozitorijum
1. Napravi novi GitHub nalog, npr. **FeatheredGossip**. Adresa sajta biće `https://featheredgossip.github.io`.
2. Napravi repozitorijum **tačno** imena `featheredgossip.github.io` (ime naloga malim slovima + `.github.io`), **Public**.
3. Ubaci sve fajlove iz ovog foldera (*Add file → Upload files*, prevuci sve fajlove i foldere).
   Folder `.github` je skriven na računaru. Ako ga GitHub ne prihvati, napravi ga ručno: *Add file → Create new file*,
   za ime upiši `.github/workflows/blog.yml` i nalepi sadržaj fajla `blog.yml`.
4. Ako ti se nalog ne zove FeatheredGossip, otvori `site_config.json` i promeni `site_url` na
   `https://TVOJE-IME.github.io`.

### 2. GitHub Pages
*Settings → Pages → Build and deployment → Source:* izaberi **GitHub Actions**.

### 3. Ključevi (Settings → Secrets and variables → Actions → New repository secret)
| Ime | Odakle | Obavezno |
|---|---|---|
| `GEMINI_API_KEY` | isti ključ kao za bota za dizajne | da |
| `APIFY_TOKEN` | apify.com → Settings → API & Integrations → Personal API token | da (za čitanje shopa) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | isti kao za bota za dizajne | ne (javlja kad izađe članak) |
| `FAL_KEY` | isti kao za bota za dizajne | ne (rezervna slika ako dizajn ne može da se preuzme) |

**Apify:** napravi besplatan nalog na apify.com (bez kartice, 5 $ kredita mesečno). Otvori alat
`solidcode/redbubble-com-scraper` na Apify-ju i pokreni ga jednom ručno sa adresom
`https://www.redbubble.com/people/WolfBeat-Shop/shop`. Tako potvrdiš da radi i vidiš svoje dizajne.
Bot ga zove jednom nedeljno sa najviše 120 proizvoda, što košta oko 0,60 $ nedeljno i staje u besplatnih 5 $.

### 4. Prvi članak
*Actions → Feathered Gossip blog → Run workflow*: `posts` = 1, `refresh_shop` = 1. Za 3-6 minuta članak je na sajtu.
Posle toga bot radi sam svako jutro.

### 5. Google Search Console (važno za SEO)
1. search.google.com/search-console → *Add property* → *URL prefix* → `https://featheredgossip.github.io/`.
2. Izaberi verifikaciju **HTML tag**, kopiraj samo vrednost `content="..."` i upiši je u `site_config.json` kod
   `google_site_verification`. Sačuvaj (sajt se sam ponovo izgradi za 1-2 minuta), pa klikni *Verify*.
3. *Sitemaps* → upiši `sitemap.xml` → *Submit*.

### 6. Pinterest (opciono, mnogo saobraćaja za ovu nišu)
Pinterest Business nalog → *Claim website* (vrednost upiši u `pinterest_verification`) → *Bulk create Pins →
Auto-publish* sa RSS adresom `https://featheredgossip.github.io/feed.xml`. Svaki novi članak postaje pin.

## Svakodnevno

- **Brisanje članka:** obriši `data/posts/IME.json`. Sajt se sam ponovo izgradi i članak nestaje.
- **Članak o određenoj ptici:** *Run workflow*, upiši `bird` (npr. `blue tit`) i po želji `angle`.
- **Novi dizajni:** bot ih sam nađe pri sledećem nedeljnom čitanju shopa. Ako ne želiš da čekaš, pokreni
  workflow sa `refresh_shop` = 1.
- **Ptica nije prepoznata:** dopiši je u `shop_birds.txt`.
- **Promo traka na vrhu sajta:** upiši tekst u `promo_text` (npr. „20% off stickers this week“), obriši kad prođe.
- **Kontakt na stranici About:** upiši email u `contact_email` (prikazuje se javno).

Pročitaj s vremena na vreme po koji članak. Bot proverava činjenice, ali Google preporučuje da čovek baci pogled
na sadržaj koji piše veštačka inteligencija.

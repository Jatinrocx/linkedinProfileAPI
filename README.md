# LinkedIn Profile API

A publicly hosted REST API that reverse-engineers LinkedIn's internal Voyager API to fetch structured JSON profile data from any LinkedIn profile URL.

---

## 🚀 Live API

```
https://<your-render-app>.onrender.com
```

### Quick test (no install needed)
```bash
curl "https://<your-render-app>.onrender.com/api/profile?url=https://www.linkedin.com/in/williamhgates"
```

---

## 📋 Features

- ✅ Accepts any LinkedIn profile URL format
- ✅ Returns structured JSON (name, headline, location, about, experience, education, skills, certifications, languages, profile/background images)
- ✅ Dual-layer architecture: fast Voyager API → Playwright HTML fallback
- ✅ In-memory TTL cache (1 hour) to reduce LinkedIn load
- ✅ Interactive Swagger UI at `/docs`
- ✅ Deployed publicly over HTTPS on Render

---

## 📦 Response Schema

```json
{
  "status": "success",
  "url": "https://www.linkedin.com/in/williamhgates",
  "scraped_at": "2025-08-27T16:00:00.000Z",
  "source": "voyager",
  "profile": {
    "public_id": "williamhgates",
    "full_name": "Bill Gates",
    "first_name": "Bill",
    "last_name": "Gates",
    "headline": "Co-chair, Bill & Melinda Gates Foundation",
    "profile_picture_url": "https://media.licdn.com/...",
    "background_image_url": "https://media.licdn.com/...",
    "location": {
      "city": null,
      "region": "Washington",
      "country": "United States",
      "full": "Seattle, Washington, United States"
    },
    "about": "Sharing things I'm learning through my foundation work...",
    "open_to_work": false,
    "hiring": false,
    "connections_count": "500+",
    "followers_count": 35000000,
    "experience": [
      {
        "company": "Bill & Melinda Gates Foundation",
        "company_linkedin_url": "https://www.linkedin.com/company/bill-melinda-gates-foundation",
        "company_logo_url": "https://media.licdn.com/...",
        "title": "Co-chair",
        "location": "Seattle, WA",
        "started_at": { "month": null, "year": 2000 },
        "ended_at": null,
        "is_current": true,
        "description": null
      }
    ],
    "education": [...],
    "skills": ["Philanthropy", "Global Health", "..."],
    "certifications": [...],
    "languages": [...],
    "honors_awards": [...],
    "publications": [...],
    "volunteer_work": [...],
    "projects": [...]
  }
}
```

---

## 🔌 API Endpoints

### `GET /`
Health check.

**Response:**
```json
{ "status": "ok", "service": "LinkedIn Profile API", "version": "1.0.0" }
```

---

### `GET /api/profile?url=<linkedin_url>`
Fetch a LinkedIn profile via GET (easy for testing in browser).

**Query Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `url` | string | ✅ | LinkedIn profile URL |

**Example:**
```bash
curl "https://<host>/api/profile?url=https://www.linkedin.com/in/williamhgates"
```

---

### `POST /api/profile`
Fetch a LinkedIn profile via POST with a JSON body.

**Request Body:**
```json
{
  "url": "https://www.linkedin.com/in/williamhgates"
}
```

**Example:**
```bash
curl -X POST https://<host>/api/profile \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.linkedin.com/in/williamhgates"}'
```

---

### `GET /docs`
Interactive Swagger UI for exploring and testing all endpoints.

### `GET /redoc`
ReDoc API reference documentation.

---

## 🏗️ Technical Approach

### Architecture: Dual-Layer Scraping

```
Request
   │
   ▼
Layer 1: LinkedIn Voyager API (httpx)
   ├── Success  ──────────────────────────────► Return structured JSON
   └── Failure (network/auth/parse error)
           │
           ▼
   Layer 2: Playwright Stealth Browser (fallback)
           └── Parse rendered HTML ───────────► Return structured JSON
```

### Layer 1 — LinkedIn Voyager API (Primary)

LinkedIn's web frontend communicates with an **internal REST API called "Voyager"**. By reverse-engineering these requests (via browser DevTools Network tab), we can make direct HTTP calls that return perfectly structured JSON — no HTML parsing needed.

**Key endpoint used:**
```
GET https://www.linkedin.com/voyager/api/identity/profiles/{public_id}/profileView
```

**Authentication:** Two cookies from an active LinkedIn browser session:
- `li_at` — primary session token
- `JSESSIONID` — used to derive the `csrf-token` request header

The challenge explicitly permits using your own LinkedIn credentials, making this the cleanest, most reliable approach.

**Why this is better than HTML scraping:**
- Returns clean, structured JSON (no selector maintenance)
- Faster (no browser overhead)
- More stable (API changes less frequently than HTML)

### Layer 2 — Playwright Stealth Browser (Fallback)

When Voyager returns unexpected responses (e.g., after LinkedIn updates an endpoint), we fall back to a headless Chromium browser via Playwright:

- Injects `li_at` / `JSESSIONID` cookies into the browser context
- Overrides `navigator.webdriver`, plugins, and language fingerprints
- Blocks unnecessary resources (images, fonts) for speed
- Parses rendered HTML with BeautifulSoup

### Caching

An in-memory TTL cache (1 hour) stores results for previously fetched `public_id`s. This:
- Makes repeat requests instant
- Reduces LinkedIn API calls (protects the account)
- Improves API performance under load

---

## 🛠️ Local Setup

### Prerequisites
- Python 3.11+
- pip

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/linkedinProfileAPI.git
cd linkedinProfileAPI
```

### 2. Create a virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your LinkedIn cookies:

**How to get them:**
1. Open Chrome and log in to LinkedIn
2. Press `F12` → **Application** tab → **Cookies** → `https://www.linkedin.com`
3. Copy the value of `li_at` → paste as `LI_AT=...`
4. Copy the value of `JSESSIONID` → paste as `JSESSIONID=...`
5. Save `.env`

> ⚠️ **Important:** Use a secondary/burner LinkedIn account to avoid risking your main account. These cookies grant full session access.

### 5. Run the server
```bash
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### 6. Test it
```bash
curl "http://localhost:8000/api/profile?url=https://www.linkedin.com/in/williamhgates"
```

---

## ☁️ Deployment (Render.com)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/linkedinProfileAPI.git
git push -u origin main
```

### 2. Create a Render Web Service
1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repository
3. Render will auto-detect the `Dockerfile`
4. Set the following **Environment Variables** in the Render dashboard:
   - `LI_AT` → your LinkedIn `li_at` cookie value
   - `JSESSIONID` → your LinkedIn `JSESSIONID` cookie value

> 🔒 **Never** put real credentials in `render.yaml` or commit them to git. Always use the Render dashboard's secret env var feature.

### 3. Deploy
Click **Create Web Service**. Render builds the Docker image, installs Chromium, and deploys. Your public HTTPS URL will look like:
```
https://linkedin-profile-api.onrender.com
```

---

## ⚠️ Known Limitations

| Limitation | Details |
|---|---|
| **LinkedIn ToS** | Automated access violates LinkedIn's User Agreement. This project is for educational/challenge purposes. |
| **Cookie expiry** | `li_at` and `JSESSIONID` cookies expire periodically. When you see 401 errors, refresh them from your browser. |
| **Rate limits** | LinkedIn rate-limits aggressive scraping. The built-in TTL cache minimizes repeat requests. |
| **Private profiles** | Profiles set to "Private" return minimal or no data. |
| **Endpoint drift** | Voyager API endpoints are undocumented and may change without notice. |
| **Render cold starts** | On the free tier, Render sleeps services after 15 min of inactivity. The first request after sleep takes ~30s. |
| **No proxy rotation** | This implementation uses a single residential IP. High-volume usage risks rate limiting. |
| **DOM changes** | The Playwright HTML fallback uses CSS selectors that may break when LinkedIn updates its frontend. |

---

## 📁 Project Structure

```
linkedinProfileAPI/
├── app/
│   ├── main.py                    # FastAPI app, routes, middleware, caching
│   ├── scraper/
│   │   ├── voyager.py             # Layer 1: Voyager API via httpx
│   │   └── playwright_scraper.py  # Layer 2: Playwright HTML fallback
│   ├── models/
│   │   └── profile.py             # Pydantic response models
│   └── utils/
│       └── url_parser.py          # LinkedIn URL parsing utilities
├── .env.example                   # Credential template (no real values)
├── .gitignore                     # Excludes .env and caches
├── Dockerfile                     # For Render deployment (includes Chromium)
├── render.yaml                    # Render deployment config
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

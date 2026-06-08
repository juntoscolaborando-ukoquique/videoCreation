# Troubleshooting



## Picsum images don't match my prompts

**Symptom:** The generated images are consistent across runs but have nothing to do with the text prompts (e.g., a prompt for "a classroom" returns a photo of a mountain).

**Cause:** Picsum is a stock photo library, not an AI generator. Its seed endpoint (`picsum.photos/seed/{seed}/...`) is deterministic but not semantic — it assigns a random photo to a seed string without understanding what the text means.

**Fix:** Picsum is now only used as a last resort fallback or when `image_engine: picsum` is explicitly set. By default the pipeline goes straight to Cloudflare Workers AI → SiliconFlow → HuggingFace. Make sure your `.env` has at least one of those keys configured. See the Pollinations 402 entry below for provider details.


## Pollinations returns HTTP 402 on VPS / cloud servers

**Symptom:** All image generation attempts via Pollinations fail with `HTTP 402`, and the pipeline falls back to Picsum (which returns unrelated random photos).

**Cause:** Pollinations.ai blocks requests from datacenter and VPS IP ranges (AWS, DigitalOcean, Hetzner, etc.) with a `402 Payment Required` response. This affects all server-side usage regardless of URL parameters or model. Confirmed via direct `curl` — every Pollinations endpoint returns 402 from a cloud IP.

**Current behavior:** Pollinations is still in the provider chain but will be skipped automatically when it returns 402. The pipeline continues to the next available provider.

**Provider priority (as of v0.3.0):**
1. Cloudflare Workers AI — works on all IPs, requires `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`
2. SiliconFlow — works on all IPs, requires `SILICONFLOW_API_KEY`
3. Pollinations — free, no key, but **blocked on VPS/datacenter IPs**
4. HuggingFace — requires `HUGGINGFACE_API_KEY`
5. Picsum — last resort, random photos (not prompt-matched)

**Fix:** Add at least one of the following to your `.env`:

```env
# Option 1 — Cloudflare (recommended, fast)
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token

# Option 2 — SiliconFlow
SILICONFLOW_API_KEY=your_key

# Option 3 — HuggingFace
HUGGINGFACE_API_KEY=your_key
```

Then set `image_engine: siliconflow` (or `cloudflare`) in your config yaml to skip straight to the working provider without waiting for Pollinations to fail first.
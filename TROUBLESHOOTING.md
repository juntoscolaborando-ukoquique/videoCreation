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

## Cloud
flare falla en una imagen y el batch entero cae a placeholders

**Síntoma:** Las primeras imágenes se generan bien, pero una falla (HTTP 400 NSFW o conexión cortada) y el resto del batch aparece como placeholders grises con texto en lugar de imágenes AI.

**Causa original:** `_try_cloudflare()` hacía `break` al primer error, abandonando todas las imágenes pendientes. Si el batch resultaba incompleto (menos imágenes que prompts), devolvía lista vacía y el pipeline caía al generador de placeholders Pillow para todas las imágenes restantes.

**Fix aplicado (image_adapter.py):** Cada prompt ahora reintenta hasta 3 veces con espera incremental (5s, 10s) antes de rendirse. Los errores se tratan según su tipo:
- Errores de conexión/timeout → reintenta hasta 3 veces
- HTTP 400 (NSFW o prompt inválido) → salta la imagen inmediatamente sin reintentar, el prompt no va a pasar el filtro
- HTTP 401 (credenciales inválidas) → aborta el proveedor completo

Con reintentos, los fallos transitorios de red se resuelven solos y los fallos por filtro NSFW se resuelven reescribiendo el prompt para evitar términos que el modelo detecta como sensibles (anatomía, fluidos corporales, descripciones de tejido) aunque el contexto sea médico.

**Por qué no se implementó fallback a imagen anterior para slots fallidos:** Cuando una imagen individual agota los reintentos, el batch devuelve vacío y el pipeline usa placeholders. Un enfoque alternativo sería reutilizar la imagen del slot anterior para mantener imágenes AI en todo el video. Esto no se implementó porque añade complejidad innecesaria: con reintentos los fallos transitorios ya se absorben, y los fallos permanentes (API caída, credenciales inválidas) afectan todo el batch de todas formas, no un slot individual. La solución correcta ante un fallo permanente es corregir el prompt o las credenciales, no enmascarar el problema con una imagen repetida.

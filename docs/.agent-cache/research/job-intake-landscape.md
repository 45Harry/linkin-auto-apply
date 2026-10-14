# Job intake landscape (researched 2026-10-14)

Verified = read from an official page during this research. Unverified = from memory or a secondary source, not checked.

## 1. Web search APIs for site: queries

- **Google Custom Search JSON API**: CLOSED to new customers. Discontinued 2027-01-01 for existing customers, then errors with no grace period. Pre-closure quota was 100 queries/day free, then $5 per 1,000 up to 10k/day. Google points to Vertex AI Search (up to 50 domains) and a partner-only full-web option. Verified: https://developers.google.com/custom-search/v1/overview . Do not build on it.
- **Brave Search API**: no open-ended free plan for new signups. Current model is $5/month free credit on Search and on Answers (applied automatically, ~1,000 Search queries), a card is required, Search is $5 per 1,000 requests. AI grounding (Answers) is $4 per 1,000 plus $5 per million tokens. Verified on https://brave.com/search/api/ . Secondary sources disagree on whether any free tier remains.
- **Bing Web Search API**: retired 2025-08-11. Microsoft's replacement is Grounding with Bing inside Azure AI Agents, which does not return raw results. Not usable. Sources: https://www.theregister.com/2025/05/15/bing_search_apis_retired/ (unverified official page, secondary report).
- **Serper, SerpAPI, Tavily, Exa**: not checked in this research. Their free tiers were not verified. Check current pricing pages before choosing one.
- **SearXNG (self-hosted)**: no API key and no per-query cost. Runs on the Oracle VM. Quality depends on which upstream engines are enabled, and those engines can rate-limit or block a datacenter IP. Not verified in this session.

**Recommendation for 24 to 100 queries/day:** self-hosted SearXNG on the Oracle VM as the primary, with the Brave $5/month credit as a capped fallback. Brave's credit covers roughly 33 queries/day, so it does not cover 100/day on its own. If SearXNG proves unreliable against LinkedIn-indexed queries, the fallback is a paid tier of Brave or Serper (pricing unverified). Test before committing.

## 2. Public ATS job board JSON endpoints

Verified: none (fetch budget was exhausted before these pages could be read). Shapes below are from memory and need a live test (`curl`) before implementation.

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{token}/jobs` (add `?content=true` for descriptions). Date fields are believed to be `updated_at` and `first_published`. Unverified.
- Lever: `https://api.lever.co/v0/postings/{company}?mode=json`. Believed to include `createdAt` as epoch milliseconds. Unverified.
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{board}`. Believed to include `publishedAt`. Unverified.
- Workable: `https://apply.workable.com/api/v1/widget/accounts/{subdomain}`. Shape and date field unverified; v3 may be the current form.

Run a live check on one known board per ATS to confirm the URL and whether a published date is present.

## 3. Gmail API (personal app)

- Verified (Google OAuth docs, https://developers.google.com/identity/protocols/oauth2#expiration): an app with publishing status "Testing" gets refresh tokens that expire in 7 days, unless the requested scopes are limited to name, email, and profile. gmail.readonly is outside that list, so the 7-day expiry applies.
- Verified: refresh tokens expire after 6 months of non-use. Limit of 100 refresh tokens per Google Account per OAuth client ID.
- Workaround for a single user: set the consent screen to "In production" (no verification needed for personal use; the user gets an "unverified app" warning and must click through). Unverified: the restricted-scope review requirement for gmail.readonly in production. Google may require verification for restricted scopes and a security assessment. Check the current restricted-scope policy before relying on it. Re-authorize after the switch so the new token is not a 7-day one.
- gmail.send: believed to be a sensitive (not restricted) scope. Unverified. Sending mail to self is the simplest case.

## 4. Oracle Cloud Always Free Ampere A1

- Verified (https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm): **2 OCPUs and 12 GB RAM total**, flexible. This is 1,500 OCPU-hours and 9,000 GB-hours per month. Not the 4 cores and 24 GB in the brief. Plan for 2 OCPU and 12 GB.
- Verified: a single instance using all resources, or up to two instances of 1 OCPU each.
- Verified idle reclamation: an instance is idle if, over a 7-day period, the 95th percentile CPU is under 20%, network is under 20%, and memory is under 20% (A1 only). Idle instances may be reclaimed. A scheduled poll job that keeps CPU or memory above the threshold avoids this. Keep a light heartbeat that is not counted as idle.

## 5. Cheapest models and free tiers

- **Anthropic**: the official models page redirected to platform.claude.com and was not fetched. Reported in secondary sources (unverified): Claude Haiku 5.5 at $0.10 input / $0.50 output per million tokens, with no model ID found. Claude Haiku 4.5 is $1.00 / $5.00 with ID `claude-haiku-4-5-20251001` (from a source URL). Verify the current ID and price at https://platform.claude.com/docs/en/about-claude/models/overview before use.
- **xAI Grok**: verified (https://docs.x.ai/developers/models). Cheapest text model is `grok-build-0.1` at $1.00 input / $2.00 output per million tokens (under 200k prompt). Next tier is `grok-4.3` and `grok-4.20-*` at $1.25 / $2.50. No free tier text on the page.
- **Google Gemini API free tier**: the rate-limits page is dated 2026-10-13. The per-model RPM/RPD table was not in the fetched content, so specific free-tier models and limits are unverified. Check the free-tier table in AI Studio (https://ai.google.dev/gemini-api/docs/rate-limits , "View your active rate limits in AI Studio"). Free tier is available with an active project and no billing required.
- **Hugging Face Inference Providers**: verified (https://huggingface.co/docs/inference-providers/pricing). Free users get **no monthly credits**; they must buy credits. PRO gets $2.00/month. So the free tier is effectively zero for a free account.
- **Ollama models for JSON extraction on 4 ARM cores and 24 GB**: not verified. Note the VM actually has 2 OCPU and 12 GB. Candidates to test: small instruct models around 1.5B to 3B parameters (e.g. Qwen2.5 3B-class or Llama 3.2 3B-class) quantized to Q4. Benchmark latency on the VM before use.

## Freshness notes

- Google Custom Search: closure and 2027-01-01 shutdown confirmed on Google's own page (2026).
- Brave: pricing confirmed on brave.com. Free-credit model reported in secondary sources as of 2026.
- Bing: retirement dated 2025 (secondary sources).
- Gemini rate-limits page: last updated 2026-10-13.
- Oracle: limits and reclamation policy from the official page (current at fetch time).
- Anthropic and Ollama: unverified.

## Confirmed links (official, fetched)

- https://developers.google.com/custom-search/v1/overview
- https://brave.com/search/api/
- https://developers.google.com/identity/protocols/oauth2#expiration
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://docs.x.ai/developers/models
- https://huggingface.co/docs/inference-providers/pricing

## Not verified (open items)

- Serper, SerpAPI, Tavily, Exa free tiers
- All four ATS JSON endpoint shapes
- Gmail restricted-scope production requirements; gmail.send classification
- Anthropic current Haiku ID and price (platform.claude.com page redirected, not fetched)
- Gemini free-tier model names and limits
- Ollama model choices

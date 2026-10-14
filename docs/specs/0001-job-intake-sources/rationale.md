# 0001. Job intake: rationale

Decision record for [index.md](index.md). `/develop` builds from `index.md`; this file explains why.

## Context

> ⚠️ Premise note: The product you described (watch LinkedIn, apply automatically, email managers with your CV) spans at least five separate decisions: job intake, matching, tailored CV generation, manager outreach email, and application submission. This spec covers only intake, the foundation the others build on. Separately, a fully automatic system that sends emails in your name to strangers fails in a known way: one bad match or a wrong name goes straight to a real hiring manager and can't be taken back, and bulk cold email gets your Gmail flagged as spam. The outreach spec should seriously weigh an approval step (one tap per email) before going fully automatic.

You want new jobs and hiring posts gathered automatically, within about an hour of posting, matched against your CV, GitHub, and LinkedIn profile, and acted on only when they are less than 14 days old. You want it fully hands off after a one time setup, you don't want to pay for data, and you don't want your LinkedIn account restricted or banned. You are in Nepal and want the companies in the community list `mesaugat/tech-companies-in-nepal` followed as well.

The core tension is that LinkedIn is where most of the signal lives, and LinkedIn's User Agreement forbids scraping and automated actions on accounts and actively detects them. The usual outcome is a restricted account, which here would mean losing the account recruiters use to find you. Your home feed in particular can only be read by something logged in as you. Paid third party providers sell LinkedIn data gathered with their own accounts, but they cost money, sit in a legal gray area, and get shut down (at least one well known provider closed in 2025).

Several free building blocks shifted recently. Google's Custom Search JSON API is closed to new customers and ends on 1 January 2027, and Bing's Web Search API was retired in August 2025. Brave now gives a $5 monthly credit (about 1,000 queries) instead of a free plan, with a card required. Hugging Face no longer gives free users monthly credits. Gmail OAuth apps left in "Testing" mode lose their refresh tokens every 7 days. Oracle's Always Free ARM allowance is 2 OCPUs and 12 GB RAM, and instances that look idle for 7 days can be reclaimed.

Many Nepali tech companies don't host their jobs on the big career board platforms, so free board feeds alone won't cover that list. Their jobs mostly appear on LinkedIn company pages, their own sites, and local job boards.

## Options considered

### Option 1: Browser bot on your own LinkedIn session

A headless browser logs in with your session and reads your feed and job searches every hour (and optionally clicks Easy Apply).

**Pros**:
- Sees exactly your feed and every LinkedIn job, with the freshest data.
- No outside data provider, no cost.

**Cons**:
- Breaks LinkedIn's terms; detection leads to restriction or a ban of your main account.
- Fragile: breaks when LinkedIn changes its page or adds checks.
- You ruled out any account risk.

### Option 2: Paid LinkedIn data provider

A third party API searches public LinkedIn posts and jobs using its own access.

**Pros**:
- Fully automatic, broad coverage of hiring posts, your account untouched.
- Structured data, so less parsing.

**Cons**:
- Monthly cost, which you ruled out.
- Legal gray area; providers get sued or shut down, so it needs a swappable adapter anyway.

### Option 3: Legitimate feeds only (Gmail, public career boards, self hosted search) (chosen)

LinkedIn alert and notification emails read through the Gmail API, public career board feeds (Greenhouse, Lever, Ashby, Workable) for your list and discovered companies, and public LinkedIn posts found through self hosted SearXNG with capped Brave as fallback. A local first AI parser structures everything.

**Pros**:
- Zero account risk and near zero cost.
- Every source is data you already receive or that is public.
- One uniform pipeline (raw item, parse, upsert), so sources are easy to add or drop.

**Cons**:
- Partial coverage: misses unindexed posts and LinkedIn jobs outside your alerts.
- LinkedIn alerts come at most daily; search indexing lags hours to days.
- SearXNG gets blocked at times; LinkedIn email templates change.

### Option 4: One click capture while you browse

A browser extension button you press on a post or job while scrolling LinkedIn yourself.

**Pros**:
- Captures exactly what you judge relevant, at zero risk (a human action).
- Very simple to build.

**Cons**:
- Manual, which you explicitly rejected.
- Coverage depends on how much you scroll.

## Rationale

Option 3 is the only one that meets all three of your hard constraints at once: fully automatic, no account risk, and no data cost. Option 1 fails the risk constraint and Option 2 fails the cost constraint. Option 4 fails the hands off constraint. The coverage gap of Option 3 is real but narrower than it looks. The posts most valuable for outreach come from people in your network, and LinkedIn already emails you about those. Public posts outside your network are reachable through search. The 14 day window absorbs the indexing and daily alert lag. (basis: least privilege and terms of service compliance for third party platforms)

On the stack: Python with Pydantic gives the strongest libraries for Gmail, email and HTML parsing, and validating AI JSON output. SQLite fits one user and a few thousand rows a month, and leaves RAM for Ollama on a 12 GB machine. One container with an in process scheduler keeps a single SQLite writer and a single thing to restart. The AI router is about 100 lines of our own code over two SDKs, because Ollama, xAI, and Gemini all offer OpenAI compatible endpoints. That beats a large abstraction dependency. Docker Compose makes the Mac test setup and the VM identical. (basis: installed `docker-compose-patterns` and `pydantic` skills; boring technology over new)

Where your preference differs from my recommendation, here is the honest account:
- **Idle reclamation.** I recommended upgrading the Oracle account to Pay As You Go, which keeps Always Free resources at $0 and is exempt from idle reclamation. You chose a keep alive approach. It works: Oracle's rule needs CPU, network, and memory all under 20% to call the VM idle, so keeping enough Ollama model memory resident (sized to about 30% of RAM, since one small model alone sits right at the 20% line) holds memory use above it. But it depends on Oracle not changing the rule, and a reclaimed VM means about 30 minutes to redeploy (data loss is small, since everything purges at 30 days). The daily memory check alerts you before that becomes a surprise.
- **Provider order.** Grok comes before Gemini at your request. Gemini's free tier would usually be cheaper as the second fallback than paid Grok. The order is a config value, so it costs nothing to change later.
- **Criteria without a confirm step.** You chose fully automatic criteria. That's workable, but a bad extraction silently changes what gets searched. The LinkedIn alerts email (AC-12) doubles as a passive view of the current criteria, so you see them whenever they change.

The Nepal list is followed through career board detection plus a per company search rotation instead of LinkedIn bell notifications. Belling hundreds of company pages by hand would break hands off operation. A stateless rotation (the position is computed from the hour) covers the whole list every few days without extra state. (basis: idempotent, stateless scheduling)

## References

**Project sources**:
- Installed skills: `docker-project-foundations`, `docker-compose-patterns`, `docker-build-strategies` (`docker/skills`), `pydantic` (`pydantic/skills`), `searxng-search` (`ypares/agent-skills`), `oci` (`oracle/skills`), all in `.claude/skills/`
- Landscape research cache: `docs/.agent-cache/research/job-intake-landscape.md`
- Tool discovery cache: `docs/.agent-cache/tool-discovery/job-intake.md`
- Company list: `mesaugat/tech-companies-in-nepal` on GitHub (named by you)

**Practices & standards**:
- Terms of service compliance and least privilege for third party platforms and OAuth scopes
- Idempotent writes with natural unique keys (`INSERT ... ON CONFLICT`)
- Boring technology over new; a single writer for SQLite
- Data minimization and time limited retention for third party personal data

**Links** (web verified on 2026-10-14):
- Google Custom Search JSON API overview (closed to new customers, ends 2027-01-01): https://developers.google.com/custom-search/v1/overview
- Brave Search API plans: https://brave.com/search/api/
- Google OAuth refresh token expiration (7 days in Testing): https://developers.google.com/identity/protocols/oauth2#expiration
- Oracle Always Free resources and idle reclamation: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Gemini API rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- xAI models and pricing: https://docs.x.ai/developers/models
- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/pricing

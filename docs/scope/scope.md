# Scope: LinkedIn job auto apply

**Product**: a hands off system that finds new jobs and hiring posts matching your profile, prepares a tailored CV, and reaches out to the hiring manager.
**Approach**: Tracer Bullet (assumed; no approach recorded yet)
**Workflow:** Beta

## At a glance

| Feature | Status | Spec |
|---|---|---|
| Job intake | in-progress | [0001](../specs/0001-job-intake-sources/index.md) |
| Matching and fit scoring | planned · needs a decision | none |
| Tailored CV generation | planned · needs a decision | none |
| Manager outreach email | planned · needs a decision | none |
| Application submission and approval | planned · needs a decision | none |

## Job intake · in-progress

Find new jobs and hiring posts every hour from LinkedIn emails, public career boards (including the Nepal tech companies list), and public web search, with no LinkedIn account risk and near zero cost.
Done when: `ready` jobs appear hourly from all four sources, deduplicated and within 14 days, with failure alerts working, running hands off on the Oracle VM.
Spec: [0001](../specs/0001-job-intake-sources/index.md)
Code: src/jobbot/

- [x] Design it (spec)
- [ ] Build it: /develop job intake
  - [x] Foundation and tracer bullet: scaffold, Compose, schema, one Greenhouse board to `ready` jobs, Gmail setup and health alerts (AC-3, AC-5, AC-15, AC-17, AC-18, AC-20)
  - [x] AI parsing and Gmail sources: AI router with caps and benchmark, alert and notification emails, dates, filter, contacts (AC-1, AC-2, AC-6, AC-7, AC-8, AC-9, AC-10)
  - [ ] Profile and companies: criteria from CV, GitHub, and LinkedIn PDF, alerts email, all board adapters, Nepal list, discovery, weekly digest (AC-3, AC-11, AC-12, AC-13, AC-14)
  - [ ] Search, retention, and deploy: SearXNG and capped Brave rotation, purge, memory keep alive, Oracle deploy and runbook (AC-4, AC-16, AC-17, AC-18, AC-19)
- [ ] Verify it: /check verify job intake
- [ ] Test it: /test job intake

## Matching and fit scoring · planned · needs a decision

Score each `ready` job against your profile and decide which ones to act on. From spec 0001.
Done when: every `ready` job gets a fit decision you can trust.

- [ ] Design it (spec)

## Tailored CV generation · planned · needs a decision

Produce a CV tailored to each matched job from your CV, GitHub, and LinkedIn profile, or use your uploaded CV as is. From spec 0001.
Done when: each matched job has a PDF CV ready to attach.
Constraint (from Harry, 2026-10-14): the generated CV must keep the exact template and format of the current CV; only the content changes. Chosen source: the Canva template via the Canva Connect API (fill the design's text fields, export a PDF). Needs the Canva template link and API credentials, kept in `data/secrets/`.

- [ ] Design it (spec)

## Manager outreach email · planned · needs a decision

Find the right person, source their address legitimately, write the email, attach the CV, and send from your Gmail while protecting deliverability and respecting anti spam and privacy law. From spec 0001.
Done when: outreach emails go out reliably without harming your sender reputation.

- [ ] Design it (spec)

## Application submission and approval · planned · needs a decision

Decide whether and how applications are submitted, and whether you approve each one before anything is sent in your name. From spec 0001.
Done when: the apply path and its approval rule are decided and built.

- [ ] Design it (spec)

## Deferred

- Move the Oracle account to Pay As You Go if the keep alive approach ever fails.

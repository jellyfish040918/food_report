# Railway deployment

## Intended release

The first deployment is a **private pilot**, not a public paid SaaS launch. It uses the real `qwen3.5:9b` model, account authentication, company-scoped storage, durable jobs and the shipped source-grounding checks. Public registration, recovery email and checkout are closed. The provisioned owner receives the normal 14-day / 5-run trial. The existing `saas` mode still requires working email and Stripe configuration before launch.

The account's compute hard limit is **$10 per billing cycle**, with an $8 alert. Railway Agent spending is disabled separately; that feature is not FLAVO's model. Hitting the compute cap stops the service. It is not a promise that $10 buys a full month of AI availability. Check invoice currency, taxes and actual metered usage in Railway.

## Services

| Service | Source/config | Networking | Storage |
| --- | --- | --- | --- |
| food_report | This repository / `/railway.toml` | Railway HTTPS domain, target 4175 | Volume mounted at `/app/var` |
| flavo-model | This repository / `/deploy/model.railway.toml` | Private only, port 11434; no public domain or TCP proxy | Qwen weights included in image; no model volume required |

Use one replica for each service in the same project/environment. The model image downloads the official model during the build and fails if the download fails. It does not download models on customer requests. The 6.5 GB weights exceed Hobby's default 5 GB volume allowance; the image uses the plan's ephemeral disk instead. The web volume preserves accounts, jobs and reports across redeployments.

## Web variables

```dotenv
FLAVO_ENV=production
FLAVO_LAUNCH_MODE=private-pilot
FLAVO_DATABASE=/app/var/flavo.sqlite3
FLAVO_MODEL=qwen3.5:9b
FLAVO_MODEL_CONTEXT=8192
FLAVO_MODEL_KEEP_ALIVE=0
OLLAMA_HOST=http://flavo-model.railway.internal:11434
PORT=4175
RAILWAY_RUN_UID=0
FLAVO_PILOT_EMAIL=owner@flavo.local
```

Set `FLAVO_PILOT_PASSWORD` directly in the provider's secret Variables UI (12–128 characters). Do not commit it. Generate the web domain; Railway supplies `RAILWAY_PUBLIC_DOMAIN`, from which the start script derives `FLAVO_PUBLIC_URL`. Do not put a GitHub Pages URL here. The runtime requires the actual `/app/var` volume, fixes only that directory's ownership, and drops root before handling requests. It never publishes the development demo or imports the developer's local database.

The pilot account is created only when the database has no users. A restart or an edited password variable never resets an existing password. After the account has been verified by signing in, remove the bootstrap password variable from Railway. Keep a backup and an operator recovery procedure before expanding the pilot.

Use the model service's actual private domain if it differs from `flavo-model.railway.internal`. Set model replica memory to the Hobby maximum (currently shown as 8 GB in this account). A larger context or additional parallel generations may exceed that. Model keep-alive is zero and parallel generation is one to reduce idle memory; this adds cold-load latency. Measure actual usage before expanding access. CPU response times and peak memory must be verified on the deployed instance.

## Publish the entry point

After **real authenticated AI chat and report generation succeed** on the Railway HTTPS domain, set GitHub repository Actions variable `FLAVO_APP_URL` to that origin and rerun the Pages workflow. Public-site feature links transfer the selected feature and KO/EN preference through sign-in. Credentials and company briefs are submitted only to the authenticated service origin. Never expose port 11434 to browsers or embed credentials in public JavaScript.

Verify desktop and mobile widths, sign-in, AI answers with sources, a generated report, persistence across a redeploy and that unauthenticated API calls are denied. `/api/health` confirms the web worker and database, not model readiness; `/api/status` requires authentication and checks the installed model. A data-only fallback is explicitly labelled and does not count as a successful AI test.

## Before selling subscriptions

Switch to `FLAVO_LAUNCH_MODE=saas` only after configuring and testing email verification/recovery, live Stripe Checkout + signed webhooks, plan pricing, backups/recovery, source/image commercial rights, customer terms/privacy and realistic capacity. Railway Hobby blocks SMTP; the existing SMTP integration requires Pro or a separately implemented and tested transactional HTTPS mail adapter. Do not use fake SMTP/Stripe values to bypass validation. This single-process SQLite design is for a small initial deployment, not horizontal scaling.

Official provider references (checked 2026-10-11): [Pricing](https://docs.railway.com/pricing/plans), [Cost limits](https://docs.railway.com/pricing/cost-control), [Volumes](https://docs.railway.com/volumes), [Private networking](https://docs.railway.com/networking/private-networking), [Outbound mail restrictions](https://docs.railway.com/networking/outbound-networking), [Healthchecks](https://docs.railway.com/deployments/healthchecks).

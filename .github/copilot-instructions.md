````instructions
* Python environment
For running Python code, use the following command:
```bash
conda run -n finance python <script_name>.py
```
Make sure to replace `<script_name>` with the actual name of your Python script.

* API overview (Ghostfolio backend)
- API app root: `apps/api/src`
- Global prefix and versioning are configured in `apps/api/src/main.ts`
  - Prefix: `/api`
  - URI versioning enabled (default `v1`), e.g. `/api/v1/...`

* Core API wiring
- Main module registration (all API modules): `apps/api/src/app/app.module.ts`
- Shared endpoint modules (feature endpoints): `apps/api/src/app/endpoints/*`

* Important APIs and locations
- Authentication
  - Routes: `/api/v1/auth/*` (anonymous login, OAuth, WebAuthn)
  - Controller: `apps/api/src/app/auth/auth.controller.ts`
  - Service: `apps/api/src/app/auth/auth.service.ts`

- Portfolio
  - Routes: `/api/v1/portfolio/*` and `/api/v2/portfolio/performance`
  - Common routes used by scripts:
    - `GET /api/v2/portfolio/performance?range=max`
    - `GET /api/v1/portfolio/holdings`
    - `GET /api/v1/portfolio/holding/:dataSource/:symbol`
  - Controller: `apps/api/src/app/portfolio/portfolio.controller.ts`
  - Service: `apps/api/src/app/portfolio/portfolio.service.ts`

- Orders (activities)
  - Routes: `/api/v1/order/*`
  - Common route: `GET /api/v1/order`
  - Controller: `apps/api/src/app/order/order.controller.ts`
  - Service: `apps/api/src/app/order/order.service.ts`

- Market Data
  - Routes: `/api/v1/market-data/*`
  - Controller: `apps/api/src/app/endpoints/market-data/market-data.controller.ts`

- Assets and Symbol metadata
  - Routes: `/api/v1/asset/*`, `/api/v1/symbol/*`, `/api/v1/logo/*`
  - Controllers:
    - `apps/api/src/app/asset/asset.controller.ts`
    - `apps/api/src/app/symbol/symbol.controller.ts`
    - `apps/api/src/app/logo/logo.controller.ts`

- Health and runtime info
  - Routes: `/api/v1/health`, `/api/v1/info`
  - Controllers:
    - `apps/api/src/app/health/health.controller.ts`
    - `apps/api/src/app/info/info.controller.ts`

* Useful note for Python integrations
- Typical flow used by scripts:
  1. `POST /api/v1/auth/anonymous` to get JWT
  2. Use `Authorization: Bearer <authToken>` for subsequent API calls
  3. Query portfolio/orders endpoints for analysis
````

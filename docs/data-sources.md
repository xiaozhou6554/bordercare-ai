# Cross-border data sources

## Sources and what they mean

| Source | Use | Access and limits |
|---|---|---|
| 1688 supplier search | China-based supplier listings, quoted prices, seller names, URLs, and platform-reported sales text when returned | The older TOP endpoint `alibaba.open.search.daixiao.offer.get` is not a dependable new-integration path: new access may be unavailable. The project can use Onebound/万邦's third-party 1688 keyword-search API when configured. Third-party data may be cached and platform-reported sales are not independently verified. It is supply-side evidence, not overseas retail demand. |
| Amazon public pages | Public search, suggestion, and review-page fields when available | Public-page access is best-effort and can return empty results or be restricted. The application does not evade access controls. |
| Google Trends via `pytrends` | Relative search-interest trend samples | This is an unofficial client for public Trends data, not Google's official alpha API. It does not provide absolute search volume. |
| Temu Partner Platform | Authorized store operations and seller data | Seller authorization and platform/app onboarding are required; this is not a general public marketplace search feed. |

## Amazon and Google Trends research adapters

The live nine-stage research flow routes market overview and competitor analysis to Amazon public search pages. Parsed search-card fields are limited to visible ASIN, title, price, rating, review count, image URL, and product URL. Explicit ASIN detail lookups and review-page analysis are separate requests. Repeated ASIN cards are deduplicated. A CAPTCHA, HTTP 403/404, rate limit, network error, or changed page structure produces an unavailable result with best-effort request diagnostics; the adapter does not rotate identities, bypass access controls, infer sales, or fill missing fields.

Trend analysis uses the supplied `pytrends` approach with the selected marketplace locale and Google Trends region. Supported timeframes are `3m`, `6m`, `12m`, and `5y`; the request can pass the timeframe in `params.timeframe`. `HTTPS_PROXY` or `HTTP_PROXY` is used when configured. The adapter performs no automatic retries, particularly after HTTP 429. Returned values are monthly 0–100 relative-interest samples, not absolute search volume. `growth_rate` compares the means of the first and second halves of the selected range; `yoy_growth` is only populated when at least 24 monthly points are available and compares the latest 12 months with the preceding 12 months. Missing results stay unavailable and are not reported as a stable trend.

## Configure 1688 supplier search

The project retains the official TOP adapter for existing authorized credentials. Onebound exposes separate Taobao and 1688 APIs; access to one does not imply access to the other. Obtain current API access and pricing from the provider before use.

```text
ONEBOUND_API_KEY=your_provider_key
ONEBOUND_API_SECRET=your_provider_secret
ONEBOUND_1688_ENABLED=false
```

Put the credentials in `.env` and restart. With Onebound credentials, Taobao keyword search is the default because it is verified for the current account. Set `ONEBOUND_1688_ENABLED=true` only after the provider confirms 1688 search access; then the app tries 1688 first and Taobao if 1688 is unavailable. `/api/health` reports the configured route without returning keys.

The third-party provider is separate from 1688 and may return cached data. Confirm its current price, quota, allowed use, and sample results before adding paid balance. Do not pass Alibaba passwords, cookies, or TOP credentials to the provider.

## Data interpretation

### Current Onebound route

The project uses `taobao.item_search` with Onebound credentials by default. It returned results once for the current account, though a later request returned provider error 5000, so availability can vary. Taobao results are retail product leads, not verified 1688 wholesale suppliers, wholesale quotes, or minimum order quantities. Set `ONEBOUND_1688_ENABLED=true` only after Onebound confirms that 1688 search access is enabled; the application then tries 1688 first and falls back to Taobao when unavailable. Confirm the provider's current quota and pricing before repeated searches.

Taobao API documentation: [taobao.item_search](https://open.onebound.cn/help/api/taobao.item_search.html).

1688 listings are supplier-search evidence. Taobao retail listing clues are not treated as verified wholesale supplier data. Overseas demand and competition stages continue to use their selected marketplace sources. Missing MOQ, rating, revenue, or verified sales fields remain empty unless a provider returns them.

Official references:

- [1688 consignment-market search API](https://open.alitrip.com/docs/api.htm?apiId=26839)
- [Onebound 1688 keyword-search API documentation](https://open.onebound.cn/help/api/1688.item_search_new.html)
- [1688 Open Platform](https://open.1688.com/)
- [Alibaba.com Open Platform onboarding](https://openapi.alibaba.com/doc/doc.htm)
- [Temu seller authorization](https://partner.temu.com/documentation?menu_code=38e79b35d2cb463d85619c1c786dd303)


## Provider failures and evidence handling

- Empty or failed responses are not cached. This lets the next query retry after credentials or provider access are corrected.
- The report records the provider, marketplace, observation time, cache expiry, and source URL where available. A failed provider response is shown as unavailable data, never as a zero-demand conclusion.
- A successful adapter call that returns zero listings is distinguished from a failed OAuth request. Product-title language affects search results; retry with marketplace-language terms before interpreting an empty sample.

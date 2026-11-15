[English](analytics.md#english) · [Русский](analytics.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Tokens and daily spending

[Home](../README.md) · [Documentation](../docs/README.md)

> **0.1.1 is local.** These instructions describe the current source and local builds. [Published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) is the earlier release. Its download links do not provide 0.1.1.


## Scope and filters

**Tokens** and **Spending** read the request journal of saved chats on this device. Activity from other applications is excluded. Deleting a chat also deletes its local statistics.

A chat can contain requests made through both services. Each recorded attempt keeps the provider, model, currency and known dispatch date used for that request. Changing the chat’s current connection does not relabel earlier activity. USD and RUB stay separate after returning to a previously used provider.

Each page retains its own **All · OpenRouter · VSEGPT** selection, period and compatible model filter. Choose **7 days**, **30 days** or **All time**. Viewing a service does not change its key, the default for new chats or the provider of the open chat.

The model list follows the selected service and period. The same model ID from OpenRouter and VSEGPT remains two choices. An incompatible model filter is reset when you change the provider.

## Tokens

| Linux | Android emulator |
| --- | --- |
| <a href="assets/screenshots/v011-linux-tokens-en.png"><img src="assets/screenshots/v011-linux-tokens-en.png" alt="Token usage filtered by provider on Linux" width="560"></a> | <a href="assets/screenshots/v011-android-tokens-en.png"><img src="assets/screenshots/v011-android-tokens-en.png" alt="Token usage filtered by provider in an Android emulator" width="300"></a> |

*Demonstration data. Android images show an emulator.*

The page shows separate provider totals, requests, API-reported input/output/total tokens and a model table. The most-used-model bars show usage for the selected filters.

API usage, local estimates and missing values remain separate. Estimated tokens do not inflate API-reported totals. Cached and reasoning details are not added a second time. Known tokens remain visible when a cost is unknown. API fields are not an independent tokenizer check. Character prices are not converted into token counts.

Historical requests without a reliable dispatch date appear only in **All time**. They do not acquire an invented day. Empty results mean that no saved requests match the filters.

## Daily spending

| Linux | Android emulator |
| --- | --- |
| <a href="assets/screenshots/v011-linux-spending-en.png"><img src="assets/screenshots/v011-linux-spending-en.png" alt="Daily spending in separate currencies on Linux" width="560"></a> | <a href="assets/screenshots/v011-android-spending-en.png"><img src="assets/screenshots/v011-android-spending-en.png" alt="Daily spending in separate currencies in an Android emulator" width="300"></a> |

*Demonstration data. Android images show an emulator.*

The Linux example shows the 30-day RUB panel. The [OpenRouter USD panel](assets/screenshots/v011-linux-spending-usd-en.png) appears further down the same view with its own scale.

**All** shows separate OpenRouter USD and VSEGPT RUB panels. A single-service selection shows only that service. There is no combined monetary total, shared currency scale or exchange-rate conversion.

Each panel includes a daily chart, confirmed dated total, confirmed daily average and date/amount/currency table. Estimated costs have their own series and total. Days without requests show zero. Requests with unknown cost mark the total as incomplete rather than becoming free requests.

Requests are grouped by the timezone shown on the page using their original dispatch time. A later accounting update stays on that day. Undated historical amounts remain separate and are excluded from the chart and daily average.

These figures describe local recorded activity. They are not a provider account statement or a substitute for its billing information. A retry that reaches the service is another request. [Chat budgets](user-guide.md) and [provider balances](providers.md) describe different values.

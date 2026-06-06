# CSQAQ Selector

This repo now includes a separate CSQAQ selector entrypoint at `main_csqaq.py`.

## What it does

- Uses the official CSQAQ API instead of browser automation.
- Can bind your current public IP to the API whitelist.
- Pulls ranked items or search results, fetches item details, and scores them.
- Can optionally push the top picks to Feishu.

## Required setup

Add these values to `.env`:

```env
CSQAQ_API_TOKEN=your-csqaq-api-token
CSQAQ_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-csqaq-token
CSQAQ_REQUEST_TIMEOUT=15
CSQAQ_AUTO_BIND_IP=true
```

If you do not want Feishu push, leave `CSQAQ_FEISHU_WEBHOOK_URL` empty and do not pass `--notify`.

## Basic usage

Search within a keyword and rank the best candidates:

```powershell
python main_csqaq.py --search "蝴蝶刀" --page-size 20 --top-k 10 --min-price 500 --max-price 5000 --min-sell-count 5 --min-buy-count 2
```

Use the ranking API directly, without a keyword:

```powershell
python main_csqaq.py --page-size 30 --top-k 10
```

Send the selected items to Feishu:

```powershell
python main_csqaq.py --search "手套" --top-k 5 --notify

List all fetched goods directly, without detail scoring:

```powershell
python main_csqaq.py --all-pages --list-only --page-size 100
```

List all goods under a keyword:

```powershell
python main_csqaq.py --search "蝴蝶刀" --all-pages --list-only --page-size 100
```
```

## Notes

- `--search` is the safest way to start because it does not require you to know exact filter labels.
- `--all-pages` will keep paging until no more rows are returned.
- `--list-only` shows the raw fetched goods list and does not call the detail scoring API.
- Filter arguments such as `--type`, `--category`, `--quality`, and `--exterior` must match the labels used by CSQAQ.
- By default the selector favors:
  - tighter BUFF spread
  - stronger 30d/90d trend
  - better buy/sell depth
  - better recent turnover
- The scoring is rule-based. If you want a different style, the logic is in `sequoia_x/csqaq/selector.py`.

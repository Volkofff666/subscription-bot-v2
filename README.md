# subscription-bot-v2
Telegram subscription bot with Tribute integration

## Tests

Run locally:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

## Docker

Webhook по умолчанию слушает `9443` (`WEBHOOK_PORT=9443` в `.env`).

```bash
docker compose up --build -d
```

Остановка:

```bash
docker compose down
```

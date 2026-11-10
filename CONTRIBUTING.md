# Contributing to TraceBrain

Thanks for helping. TraceBrain's promise is that every answer can be checked: keep sources,
freshness, conflicts and the exact Cypher visible in anything you change.

## Ground rules

- Be kind. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Open an issue before a large change so we can agree on the approach.
- Keep pull requests focused: one change, one reason.
- Use synthetic data only. Never commit `.env` or Slack secrets.

## Setup

```bash
git clone https://github.com/boss477/graphhacks.git
cd graphhacks
docker compose up falkordb -d
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or run everything with `docker compose up --build` and open http://localhost:8000.

## Before you open a pull request

- `pytest` passes.
- Answers still return their sources, freshness, conflict status, Cypher and graph path.

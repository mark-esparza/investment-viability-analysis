"""SEC EDGAR client (spec section 2.1).

Hard rules enforced here:
  * Descriptive ``User-Agent`` on every request (missing -> HTTP 403).
  * <= 10 requests/sec -> a ~120 ms floor between calls.
  * On-disk response cache so re-runs and tests don't hammer EDGAR.
  * EDGAR has no CORS; this runs server-side (CLI/backend), never in a browser.

Set the contact via the ``IVA_SEC_USER_AGENT`` env var, e.g.
``"InvestmentViability/1.0 you@example.com"``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

DEFAULT_UA = os.environ.get(
    "IVA_SEC_USER_AGENT", "InvestmentViability/1.0 contact@example.com"
)
_MIN_INTERVAL = 0.12  # seconds between requests (<10/sec, with margin)


class EdgarClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        cache_dir: Optional[Path] = None,
        offline: bool = False,
    ):
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir or Path.home() / ".cache" / "ivanalysis" / "edgar")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )

    # -- low level ----------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()

    def _cache_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"{safe}.json"

    def get_json(self, url: str, cache_key: str, ttl_hours: float = 24.0) -> dict:
        path = self._cache_path(cache_key)
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600.0
            if self.offline or age_h < ttl_hours:
                return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise FileNotFoundError(f"offline and no cache for {cache_key}")
        self._throttle()
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    # -- endpoints ----------------------------------------------------------
    def ticker_to_cik(self, ticker: str) -> Optional[str]:
        """Resolve a ticker to a 10-digit zero-padded CIK via the public map."""
        data = self.get_json(
            "https://www.sec.gov/files/company_tickers.json",
            "company_tickers",
            ttl_hours=24 * 7,
        )
        t = ticker.upper().strip()
        for row in data.values():
            if row.get("ticker", "").upper() == t:
                return str(row["cik_str"]).zfill(10)
        return None

    def company_facts(self, cik: str) -> dict:
        """All XBRL facts for a company -- the primary fundamentals source."""
        cik10 = str(cik).zfill(10)
        return self.get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
            f"companyfacts_{cik10}",
        )

    def submissions(self, cik: str) -> dict:
        cik10 = str(cik).zfill(10)
        return self.get_json(
            f"https://data.sec.gov/submissions/CIK{cik10}.json",
            f"submissions_{cik10}",
        )

    def company_concept(self, cik: str, tag: str, taxonomy: str = "us-gaap") -> dict:
        cik10 = str(cik).zfill(10)
        return self.get_json(
            f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json",
            f"concept_{cik10}_{taxonomy}_{tag}",
        )

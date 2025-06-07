# PumpSwap Watcher

**PumpSwap Watcher** is a Python module for real-time monitoring of Solana PumpSwap pools—providing live token price updates via WebSocket. It’s designed for bot creators, traders, and devs who need accurate, low-latency, faster price feeds for any SPL token on PumpSwap without relying on price APIs.

> _After facing a lack of public resources for PumpSwap/Solana pool monitoring, I built and open-sourced this for the community._

---

## Features

- **Live Price Updates:** Connects to Solana RPC/WebSocket for instant price changes in PumpSwap pools.
- **Automatic Decimal Handling:** Correctly factors in SPL token decimals for accurate price calculations.
- **Pool Account Decoding:** Decodes pool and token account structures on-the-fly.
- **Reconnect Logic:** Automatically handles dropped WebSocket connections.
- **Minimal Dependencies:** Uses standard Python libraries and `construct`, `requests`, `websockets`.

---

## Usage

### 1. Install requirements

```bash
pip install -r requirements.txt
```

### 2. Get the PumpSwap Pool Address for Your Token

You can use the included helper:

```python
# fetch_pair_addr.py example
from fetch_pair_addr import fetch_pair_addr

mint = "YourTokenMintHere"
pair_addr = fetch_pair_addr(mint)
print("Pool address:", pair_addr)
```

### 3. Run the Watcher

```python
import asyncio
from pumpswap_watcher import watch_pumpswap_pool

async def handle_price(price):
    print("Live price:", price)

POOL_ADDR = "YourPoolAddressHere"
asyncio.run(watch_pumpswap_pool(POOL_ADDR, handle_price))
```

---

## Modules

- **pumpswap_watcher.py**  
  Main module for connecting and decoding PumpSwap pools.  
  - `watch_pumpswap_pool(pool_addr, callback)` – calls your callback every time the price updates.

- **fetch_pair_addr.py**  
  Helper to get the PumpSwap pool address for any SPL token mint, using the [Dexscreener API](https://api.dexscreener.com/).

---

## Example: Full Script

```python
from fetch_pair_addr import fetch_pair_addr
from pumpswap_watcher import watch_pumpswap_pool
import asyncio

async def print_price(price):
    print("Live price:", price)

mint = "YourTokenMintHere"
pool_addr = fetch_pair_addr(mint)
if pool_addr:
    asyncio.run(watch_pumpswap_pool(pool_addr, print_price))
else:
    print("Pool not found on Dexscreener.")
```

---

## Why Open Source?

There are few resources for real-time on-chain DEX monitoring on Solana’s new DEXes. This code aims to help bot builders, traders, and tinkerers monitor PumpSwap pools directly.

**PRs, issues, and forks are welcome!**

---

## Disclaimer

- This is a developer tool. Use at your own risk.
- Always test with non-critical funds and assets.
- No affiliation with Pump.fun, PumpSwap, or Solana.

---

## License

MIT

---

## Credits

- [construct](https://construct.readthedocs.io/)
- [websockets](https://websockets.readthedocs.io/)
- [Dexscreener](https://dexscreener.com/)

#pumpswap_watcher.py
import asyncio
import base64
import json
import struct
import base58
import requests
import websockets
from construct import Struct, Int8ul, Int16ul, Bytes, Int64ul
import os
import logging
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# Configure logging
def setup_logger(name="pumpswap_watcher") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.hasHandlers():
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
logger = setup_logger()

# Solana endpoints
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=<your-api-key>")
WS_URL = os.getenv("WS_ENDPOINT", "wss://rpc.helius.xyz/?api-key=<your-api-key>")

# PumpSwap Pool struct
Pool = Struct(
    "discriminator" / Bytes(8),
    "pool_bump" / Int8ul,
    "index" / Int16ul,
    "creator" / Bytes(32),
    "base_mint" / Bytes(32),
    "quote_mint" / Bytes(32),
    "lp_mint" / Bytes(32),
    "pool_base_token_account" / Bytes(32),
    "pool_quote_token_account" / Bytes(32),
    "lp_supply" / Int64ul,
)

def fetch_pool_info_from_json(json_response):
    try:
        value = json_response.get("result", {}).get("value")
        if not value or not value.get("data"):
            logger.error("Invalid pool account data: %s", json_response)
            return None, None, None, None
        b64_data = value["data"][0]
        raw_data = base64.b64decode(b64_data)
        parsed = Pool.parse(raw_data)
        base_vault_addr = base58.b58encode(parsed.pool_base_token_account).decode()
        quote_vault_addr = base58.b58encode(parsed.pool_quote_token_account).decode()
        base_mint = base58.b58encode(parsed.base_mint).decode()
        quote_mint = base58.b58encode(parsed.quote_mint).decode()
        return base_vault_addr, quote_vault_addr, base_mint, quote_mint
    except Exception as e:
        logger.error("Failed to parse pool info: %s", str(e))
        return None, None, None, None

def get_spl_decimals(mint_addr):
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [mint_addr, {"encoding": "base64"}]
        }
        resp = requests.post(RPC_URL, json=payload, timeout=5)
        resp.raise_for_status()
        resp_json = resp.json()
        value = resp_json.get("result", {}).get("value")
        if not value or not value.get("data"):
            logger.error("Mint address %s not found or not a mint account", mint_addr)
            return None
        data = value["data"][0]
        raw = base64.b64decode(data)
        decimals = raw[44]  # u8 at offset 44 for SPL mint account
        return decimals
    except Exception as e:
        logger.error("Failed to fetch decimals for %s: %s", mint_addr, str(e))
        return None

def parse_spl_token_account(b64_data):
    try:
        data = base64.b64decode(b64_data)
        mint = base58.b58encode(data[0:32]).decode()
        owner = base58.b58encode(data[32:64]).decode()
        amount = struct.unpack_from("<Q", data, 64)[0]
        return {"mint": mint, "owner": owner, "amount": amount}
    except Exception as e:
        logger.error("Failed to parse token account: %s", str(e))
        return None

def format_amount(amount, decimals):
    if decimals is None or amount is None:
        return amount
    return amount / (10 ** decimals)

def calculate_price(base_amt, quote_amt, base_dec, quote_dec, base_mint=None, quote_mint=None):
    # If base is SOL, invert to get SOL per token
    SOL_MINT = "So11111111111111111111111111111111111111112"
    if base_mint == SOL_MINT or base_dec == 9:
        # base is SOL, so price = (base_amt * (10**quote_dec)) / (quote_amt * (10**base_dec))
        if quote_amt == 0 or quote_amt is None or base_amt is None or base_dec is None or quote_dec is None:
            return None
        price = (base_amt * (10 ** quote_dec)) / (quote_amt * (10 ** base_dec))
        #logger.info(f"[INVERTED] calculate_price: base_amt={base_amt}, quote_amt={quote_amt}, base_dec={base_dec}, quote_dec={quote_dec}, price={price}")
        return price
    else:
        # base is token, quote is SOL: price = (quote_amt * (10**base_dec)) / (base_amt * (10**quote_dec))
        if base_amt == 0 or base_amt is None or quote_amt is None or base_dec is None or quote_dec is None:
            return None
        price = (quote_amt * (10 ** base_dec)) / (base_amt * (10 ** quote_dec))
        #logger.info(f"calculate_price: base_amt={base_amt}, quote_amt={quote_amt}, base_dec={base_dec}, quote_dec={quote_dec}, price={price}")
        return price

async def watch_pumpswap_pool(pool_addr, callback):
    """
    Watches a PumpSwap pool and calls `callback(price: Decimal)` on every price update (quote/base).
    The callback should be an async function.
    """
    # Fetch pool info with retries
    for attempt in range(3):
        try:
            resp = requests.post(RPC_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                "params": [pool_addr, {"encoding": "base64"}]
            }, timeout=5)
            resp.raise_for_status()
            json_response = resp.json()
            logger.info("Pool fetched!")
            base_vault, quote_vault, base_mint, quote_mint = fetch_pool_info_from_json(json_response)
            if None in (base_vault, quote_vault, base_mint, quote_mint):
                raise ValueError("Invalid pool info")
            break
        except Exception as e:
            logger.error("Attempt %d: Failed to fetch pool info for %s: %s", attempt + 1, pool_addr, str(e))
            if attempt == 2:
                logger.error("Giving up on pool %s after 3 attempts", pool_addr)
                return
            await asyncio.sleep(2 ** attempt)

    base_dec = get_spl_decimals(base_mint)
    quote_dec = get_spl_decimals(quote_mint)
    if base_dec is None or quote_dec is None:
        logger.error("Failed to fetch decimals for pool %s", pool_addr)
        return

    latest = {"base": None, "quote": None}
    reconnect_delay = 1
    sub_map = {}

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                logger.info("Connected to WebSocket for pool %s", pool_addr)
                reconnect_delay = 1
                # Subscribe to base and quote vaults
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "accountSubscribe",
                    "params": [base_vault, {"encoding": "base64", "commitment": "confirmed"}]
                }))
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": 2, "method": "accountSubscribe",
                    "params": [quote_vault, {"encoding": "base64", "commitment": "confirmed"}]
                }))
                # Map subscription IDs
                for _ in range(2):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    sub_id = msg.get("result")
                    if sub_id is None:
                        raise ValueError("Invalid subscription response")
                    sub_map[sub_id] = "base" if msg["id"] == 1 else "quote"

                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    if msg.get("method") != "accountNotification":
                        continue
                    sub_id = msg["params"]["subscription"]
                    kind = sub_map.get(sub_id)
                    if not kind:
                        continue
                    b64_data = msg["params"]["result"]["value"]["data"][0]
                    parsed = parse_spl_token_account(b64_data)
                    if not parsed:
                        continue
                    latest[kind] = parsed["amount"]
                    if latest["base"] is not None and latest["quote"] is not None:
                        price = calculate_price(latest["base"], latest["quote"], base_dec, quote_dec)
                        if price is not None:
                            await callback(Decimal(str(price)))
                            logger.info("Live price: %s", price)
        except Exception as e:
            logger.error("WebSocket error for pool %s: %s", pool_addr, str(e))
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 16)

"""
# Example CLI usage
if __name__ == "__main__":
    import sys
    async def print_price(price): print(f"Live Price: {price:.12f} (quote/base)")
    POOL_ADDR = sys.argv[1] if len(sys.argv) > 1 else "5fo6rn6t8697uHE744utJ9rs4HvPq9yzt8FeiFM641QW"
    asyncio.run(watch_pumpswap_pool(POOL_ADDR, print_price))
"""

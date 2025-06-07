# fetch_pair_addr.py
import requests

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

def fetch_pair_addr(mint: str) -> str | None:
    """
    Fetches the PumpSwap pool (pair) address for a mint using the Dexscreener API.
    Returns the address as a string, or None if not found.
    """
    url = f"{DEXSCREENER_API}/{mint}"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        pairs = data.get("pairs", [])
        # Filter for PumpSwap (case-insensitive match)
        for pair in pairs:
            dex_id = pair.get("dexId", "").lower()
            if "pumpswap" in dex_id or "pump-swap" in dex_id:
                return pair.get("pairAddress")
        return None
    except Exception as e:
        print(f"Error fetching pair address for {mint}: {e}")
        return None

# Example usage:
if __name__ == "__main__":
    mint = input("Enter mint address: ").strip()
    pool_addr = fetch_pair_addr(mint)
    if pool_addr:
        print("PumpSwap pool address:", pool_addr)
    else:
        print("No PumpSwap pool found for this mint.")

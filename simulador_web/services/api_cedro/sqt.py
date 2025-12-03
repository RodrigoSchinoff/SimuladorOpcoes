from .client import CedroSocketClient

async def get_spot_snapshot(ativo: str):
    """
    Executa comando SQT N <ATIVO> para obter snapshot de spot.
    """
    cmd = f"SQT N {ativo}"
    client = CedroSocketClient()
    data = await client.send_command(cmd)

    # Ajuste conforme estrutura exata retornada pela CErdro
    spot = data.get("lastPrice") or data.get("price") or data.get("spot")
    return float(spot)

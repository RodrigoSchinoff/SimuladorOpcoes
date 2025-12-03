from .client import CedroSocketClient

async def get_opcoes_vencimento(ativo: str, vencimento: str):
    """
    Executa comando GSO <ATIVO> <VENCIMENTO>
    e retorna lista completa de opções (CALL e PUT).
    """
    cmd = f"GSO {ativo} {vencimento}"
    client = CedroSocketClient()
    data = await client.send_command(cmd)

    # A Cedro normalmente retorna algo como:
    # { "options": [ { "symbol": "PETRA30", "strike": 30.0, "type": "CALL", "last": 1.50 }, ... ] }

    opcoes = data.get("options", [])     # Ajustável conforme payload exato

    resultado = []
    for o in opcoes:
        item = {
            "symbol": o.get("symbol"),
            "strike": float(o.get("strike")),
            "tipo": o.get("type"),            # CALL ou PUT
            "preco": float(o.get("last") or 0),
        }
        resultado.append(item)

    return resultado

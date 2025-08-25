from dataclasses import dataclass
from typing import List, Dict, Any, Protocol

@dataclass
class OptionLeg:
    symbol: str
    type: str        # "CALL" | "PUT"
    strike: float
    bid: float = 0.0
    ask: float = 0.0
    close: float = 0.0
    last: float = 0.0
    contract_size: int = 100
    spot_price: float = 0.0
    due_date: str = ""

@dataclass
class SimulationResult:
    estrategia: str
    precos: List[float]
    payoff: List[float]
    custo_total: float
    be_down: float | None
    be_up: float | None
    spot: float
    vencimento: str
    metrics: Dict[str, Any]

class Strategy(Protocol):
    def simulate(self, legs: Dict[str, OptionLeg]) -> SimulationResult: ...

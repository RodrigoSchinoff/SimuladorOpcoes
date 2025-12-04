from cd3_connector import CD3Connector


class CedroService:
    def __init__(self):
        self.client = CD3Connector()

    def get_spot_via_sqt(self, ticker):
        return self.client.sqt(ticker)

    def get_opcoes_via_gso(self, ticker):
        return self.client.gso(ticker)

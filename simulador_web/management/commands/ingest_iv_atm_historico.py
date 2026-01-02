from django.core.management.base import BaseCommand
from django.db import transaction

from services.iv_historica import buscar_iv_atm_historica
from simulador_web.models import IvAtmHistorico


class Command(BaseCommand):
    help = "Ingestão do histórico diário de IV ATM via OPLAB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticker",
            required=True,
            type=str,
            help="Ticker do ativo (ex: PETR4)",
        )
        parser.add_argument(
            "--from",
            dest="date_from",
            required=True,
            type=str,
            help="Data inicial (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            required=True,
            type=str,
            help="Data final (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        ticker = options["ticker"].upper()
        date_from = options["date_from"]
        date_to = options["date_to"]

        self.stdout.write(
            self.style.NOTICE(
                f"Iniciando ingestão IV ATM | {ticker} | {date_from} → {date_to}"
            )
        )

        dados = buscar_iv_atm_historica(
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
        )

        if not dados:
            self.stdout.write(self.style.WARNING("Nenhum dado retornado."))
            return

        inseridos = 0
        atualizados = 0

        with transaction.atomic():
            for d in dados:
                obj, created = IvAtmHistorico.objects.update_or_create(
                    ticker=d["ticker"],
                    trade_date=d["trade_date"],
                    defaults={
                        "spot_price": d["spot_price"],

                        "call_symbol": d["call"]["symbol"],
                        "call_due_date": d["call"]["due_date"],
                        "call_days_to_maturity": d["call"]["days_to_maturity"],
                        "call_premium": d["call"]["premium"],
                        "call_volatility": d["call"]["volatility"],

                        "put_symbol": d["put"]["symbol"],
                        "put_due_date": d["put"]["due_date"],
                        "put_days_to_maturity": d["put"]["days_to_maturity"],
                        "put_premium": d["put"]["premium"],
                        "put_volatility": d["put"]["volatility"],

                        "iv_atm_mean": d["iv_atm_mean"],
                    },
                )
                if created:
                    inseridos += 1
                else:
                    atualizados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Ingestão concluída | Inseridos: {inseridos} | Atualizados: {atualizados}"
            )
        )

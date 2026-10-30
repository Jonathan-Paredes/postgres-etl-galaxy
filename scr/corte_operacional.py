"""Plan de extracción; sin scheduler ni dependencia de Luigi."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ConfiguracionCorte:
    solapamiento_dias: int = 7
    zona: str = 'America/Santiago'
    hora: time = time(5, 30)

    def __post_init__(self):
        if type(self.solapamiento_dias) is not int or self.solapamiento_dias < 1:
            raise ValueError('solapamiento_dias debe ser entero positivo')
        ZoneInfo(self.zona)
        if self.zona != 'America/Santiago' or self.hora != time(5, 30):
            raise ValueError('El contrato operacional exige America/Santiago a las 05:30')

    def efectivo(self, referencia: datetime) -> datetime:
        if referencia.tzinfo is None or referencia.utcoffset() is None:
            raise ValueError('La referencia debe incluir zona horaria')
        local = referencia.astimezone(ZoneInfo(self.zona))
        corte = datetime.combine(local.date(), self.hora, tzinfo=ZoneInfo(self.zona))
        if local < corte:
            corte -= timedelta(days=1)
        return corte

    def validar(self, corte: datetime) -> datetime:
        if corte.tzinfo is None or corte.utcoffset() is None:
            raise ValueError('fecha_corte debe incluir zona horaria')
        local = corte.astimezone(ZoneInfo(self.zona))
        if local.timetz().replace(tzinfo=None) != self.hora:
            raise ValueError('El corte debe corresponder exactamente a las 05:30 de Santiago')
        return local

    def ventana(self, corte: datetime):
        corte = self.validar(corte)
        return corte - timedelta(days=self.solapamiento_dias), corte

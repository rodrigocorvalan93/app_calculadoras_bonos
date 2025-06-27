#%%
from utils import *

#%%

#Last version
# Obtener feriados argentinos 90-2151

# Obtener feriados argentinos y estadounidenses
ar_holidays = holidays.Argentina(years=list(range(1990, 2151)))
us_holidays = holidays.US(years=list(range(1990, 2151)))

# Agregar días festivos adicionales manualmente
additional_holidays = {
    "2023-11-06": "Día del bancario 2023",
    "2024-03-28": "Jueves Santo",
    "2024-04-01": "Dia Feriado Turístico",
    "2024-06-21": "Dia Feriado Turístico",
    "2024-10-11": "Dia Feriado Turístico",
    "2024-11-06": "Día del bancario"
}
ar_holidays.update(additional_holidays)

# Función auxiliar para convertir a datetime.date
def convertir_a_date(fecha):
    if isinstance(fecha, np.datetime64):
        return pd.to_datetime(fecha).date()
    elif isinstance(fecha, datetime):
        return fecha.date()
    elif isinstance(fecha, pd.Timestamp):
        return fecha.date()
    elif isinstance(fecha, date):
        return fecha
    else:
        raise TypeError(f"Tipo de fecha no reconocido: {type(fecha)}")

# Función para encontrar el siguiente día hábil en Argentina
def siguiente_dia_habil_ar(fecha):
    fecha = convertir_a_date(fecha)
    while fecha.weekday() >= 5 or fecha in ar_holidays:  # 5 y 6 son sábado y domingo
        fecha = (pd.Timestamp(fecha) + BDay(1)).date()
    return fecha

# Función para encontrar el siguiente día hábil en EE.UU.
def siguiente_dia_habil_us(fecha):
    fecha = convertir_a_date(fecha)
    while fecha.weekday() >= 5 or fecha in us_holidays:  # 5 y 6 son sábado y domingo
        fecha = (pd.Timestamp(fecha) + BDay(1)).date()
    return fecha

# Función para encontrar n días hábiles

def n_dias_laborales(fecha, n):
    fecha = convertir_a_date(fecha)
    if n > 0:
        while n > 0:
            fecha = (pd.Timestamp(fecha) + BDay(1)).date()  # Añade un día hábil
            while fecha.weekday() >= 5 or fecha in ar_holidays:
                fecha = (pd.Timestamp(fecha) + BDay(1)).date()  # Añade días hasta que sea un día hábil
            n -= 1
    elif n < 0:
        while n < 0:
            fecha = (pd.Timestamp(fecha) - BDay(1)).date()  # Resta un día hábil
            while fecha.weekday() >= 5 or fecha in ar_holidays:
                fecha = (pd.Timestamp(fecha) - BDay(1)).date()  # Resta días hasta que sea un día hábil
            n += 1

    return fecha

# Implementación de la función days360


# DIAS 360  
# Implementación basada en: https://github.com/tfeldmann/days360/blob/main/days360/days360.py
#
# ---------------------------------------------------------------------------
# Este módulo provee tres variantes del cómputo “30/360” (calendario de 360 días)
# ampliamente usado en finanzas para calcular intereses y cupones:
#
#   • US  / 30US/360   – Método estadounidense (NASD) tal como lo implementa Excel.  
#   • US_NASD         – Mismo método pero sin replicar el “bug” de Excel.  
#   • EU  / 30E/360    – Método europeo.  
#
# Todas las funciones aceptan y devuelven objetos `datetime.date` (formato
# AAAA-MM-DD) y retornan un entero con la cantidad de días “30/360”.
#
# IMPORTANTE ▸ No se modifican los nombres ni la firma de las funciones;
#              sólo se añaden comentarios en castellano para mayor claridad.
# ---------------------------------------------------------------------------

from datetime import date as Date  # se usan instancias de datetime.date
from datetime import timedelta     # necesario para restar días
from typing import Literal

# Literal para restringir los métodos válidos
Method = Literal["US", "US_NASD", "EU"]


def is_last_day_of_february(date: Date) -> bool:
    """
    Devuelve `True` si la fecha recibida es el último día de febrero
    (considera años bisiestos).

    Parámetros
    ----------
    date : datetime.date
        Fecha a evaluar (AAAA-MM-DD).
    """
    # El 1 de marzo menos un día ⇒ último día de febrero del mismo año
    last_february_day_in_given_year = Date(date.year, 3, 1) - timedelta(days=1)
    return date == last_february_day_in_given_year


def days360_US(
    date_a: Date,
    date_b: Date,
    preserve_excel_compatibility: bool = True,
) -> int:
    """
    Calcula la diferencia de días entre `date_a` y `date_b`
    usando el método 30US/360 (EE. UU.).

    ► Para reproducir 100 % el resultado de Microsoft Excel/Calc,
      deje `preserve_excel_compatibility=True` (valor por defecto).
      Excel arrastra un “bug” histórico que se mantiene por
      compatibilidad retroactiva; Open Office lo imitó.

    ► Si se desea la versión “de referencia” del estándar,
      pase `preserve_excel_compatibility=False`.

    Parámetros
    ----------
    date_a, date_b : datetime.date
        Fechas en formato AAAA-MM-DD.
    preserve_excel_compatibility : bool, opcional
        Mantener compatibilidad con Excel; por defecto `True`.

    Retorna
    -------
    int
        Cantidad de días expresados bajo la convención 30/360.
    """
    day_a = date_a.day
    day_b = date_b.day

    # Paso 1  (omitido si queremos compatibilidad con Excel)
    # (1) Si A y B caen ambos en el último día de febrero,
    #     entonces B se reemplaza por 30 del mismo mes.
    if (
        not preserve_excel_compatibility
        and is_last_day_of_february(date_a)
        and is_last_day_of_february(date_b)
    ):
        day_b = 30

    # Paso 2
    # (2) Si A es 31 de cualquier mes *o* último de febrero,
    #     se cambia A al día 30.
    if day_a == 31 or is_last_day_of_february(date_a):
        day_a = 30

    # Paso 3
    # (3) Si después del paso 2, A es 30 y B es 31,
    #     se cambia B al día 30.
    if day_a == 30 and day_b == 31:
        day_b = 30

    # Fórmula estándar 30/360
    days = (
        (date_b.year - date_a.year) * 360
        + (date_b.month - date_a.month) * 30
        + (day_b - day_a)
    )
    return days


def days360_US_NASD(date_a: Date, date_b: Date) -> int:
    """
    Versión NASD “pura” (sin el bug de Excel) del método 30US/360.
    Internamente llama a `days360_US` desactivando la compatibilidad.
    """
    return days360_US(date_a, date_b, preserve_excel_compatibility=False)


def days360_EU(date_a: Date, date_b: Date) -> int:
    """
    Método europeo 30E/360.

    Reglas clave
    ------------
    • Si cualquiera de las dos fechas cae en *31*, se reemplaza por 30.  
    • Si `date_b` es el último día de febrero, *no* se ajusta (se usa tal cual).  
    """
    day_a = date_a.day
    day_b = date_b.day

    if day_a == 31:
        day_a = 30
    if day_b == 31:
        day_b = 30

    days = (
        (date_b.year - date_a.year) * 360
        + (date_b.month - date_a.month) * 30
        + (day_b - day_a)
    )
    return days


def days360(date_a: Date, date_b: Date, method: Method = "US") -> int:
    """
    Función de conveniencia que expone los tres métodos:

    Parameters
    ----------
    date_a, date_b : datetime.date
        Fechas (AAAA-MM-DD).
        d1 = date.fromisoformat("YYYY-MM-DD")           → datetime.date(2025, 5, 28)
        d2 = datetime.strptime("YYYY-MM-DD", "%d/%m/%Y").date()
    method : {"US", "US_NASD", "EU"}, opcional
        Método a utilizar; por defecto "US".

    Returns
    -------
    int
        Diferencia de días 30/360 según el método elegido.
    """
    if method == "US":
        return days360_US(date_a, date_b)
    elif method == "US_NASD":
        return days360_US_NASD(date_a, date_b)
    elif method == "EU":
        return days360_EU(date_a, date_b)
    else:
        raise ValueError(f"Unknown method: {method}")


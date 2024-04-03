#%%
from utils import *
import indices
from dias_habiles import (convertir_a_date, siguiente_dia_habil_ar, siguiente_dia_habil_us,
                          n_dias_laborales, days360)
inputs = indices.main()
#Last version
#%%
class Bono:
    def __init__(self, data):
        self.nombre_security = data.get("Nombre Security")
        self.codigo = data.get("Código")
        self.isin = data.get("ISIN")
        self.calificacion = data.get("Calificación")
        self.pais = data.get("País")
        self.clasificacion = data.get("Clasificación")
        self.industria = data.get("Industria")
        self.moneda = data.get("Moneda")
        self.plazo_habitual_liquidacion = data.get("Plazo habitual de liquidación: t +")
        self.emision = datetime.strptime(data.get("Emisión"), '%d/%m/%Y').date()
        self.vencimiento = datetime.strptime(data.get("Vencimiento"), '%d/%m/%Y').date()
        self.fecha_primer_cupon = datetime.strptime(data.get("Fecha Primer Cupón"), '%d/%m/%Y') if data.get("Fecha Primer Cupón") is not None else None
        self.cupon_spread = data.get("Cupón / Spread")
        self.step_up = data.get("Step-up")
        self.frecuencia_pago_cupon = data.get("Frecuencia de pago de cupón anual")
        self.convencion_fechas_pago = data.get("Convención fechas de pago")
        self.convencion_devengamiento = data.get("Convención de devengamiento")
        self.convencion_base = data.get("Convención Base")
        self.tipo_amortizacion = data.get("Tipo de Amortización")
        self.tipo_tasa_interes = data.get("Tipo Tasa Interés")
        self.index = data.get("Index")
        self.dias_lag_indice_desde = data.get("Días Lag índice desde inc")
        self.dias_lag_indice_hasta = data.get("Días Lag índice hasta inc")
        self.valor_nominal = data.get("Valor Nominal")
        self.quote_price_cnv = data.get("Quote Price Convention")
        self.ajuste_sobre_capital = data.get("Ajuste sobre Capital")
        self.factor_capitalizacion = data.get("Factor Capitalización")
        self.dias_lag_ajuste_base = data.get("Días lag Ajuste base")
        self.dias_lag_ajuste = data.get("Días lag Ajuste")
        # self.fechas_cupon = [datetime.strptime(fecha, '%d/%m/%Y') for fecha in data.get("Fechas de cupón")] Old que traia datetime
        self.fechas_cupon = [datetime.strptime(fecha, '%d/%m/%Y').date() for fecha in data.get("Fechas de cupón")]
        self.cupones = len(self.fechas_cupon)
        fechas_cupon_numpy = np.array(self.fechas_cupon)

        self.callable = data.get("Callable")
        self.tipo_call = data.get("Tipo de Call")
        self.fecha_call = datetime.strptime(data.get("Fecha Call"), '%d/%m/%Y') if data.get("Fecha Call") is not None else None
        self.precio_call = data.get("Precio Call")
        self.aviso_resultados = data.get("Aviso Resultados")
        self.suplemento_prospecto = data.get("Suplemento Prospecto")


        #  Si no se aclara se pone por defecto "Convención de Quote Price" Dirty
        if self.quote_price_cnv == None:
           self.quote_price_cnv = 'DIRTY'
        else:
            pass

        if self.frecuencia_pago_cupon not in (1,2,4,6,12,48,365): # verifica si A no es regular con frecuencias 2,4,6,12,48,365
            self.cnv_tna = 'plazo remanente'
        else:
            self.cnv_tna = 360/self.frecuencia_pago_cupon #Antes:self.convencion_base/self.frecuencia_pago_cupon



        # Crea automáticamente las amortizaciones sólo si es bullet, siempre en % cada 100
        if self.tipo_amortizacion == 'BULLET':
           self.amortizacion = np.array([0] * (self.cupones-1) + [100])
        else:
           self.amortizacion = np.array(data.get("Amortización"))

        # Error de amortización
        if round(sum(self.amortizacion),8) != self.valor_nominal:
            raise ValueError("Error de amortización: La suma de la lista de amortización no es igual a 100 o al Valor Nominal Inicial")

        # Fechas de pago efectivo hábil: crea variable de fechas de pago posta con dia habil, si paga pesos o dolar local es considerando feriados arg sino con feriados us
        if self.moneda == 'ARS' or self.moneda == 'USB':  # Feriados ARG
            fechas_pago_cupon_habil = [siguiente_dia_habil_ar(date) for date in self.fechas_cupon]
        else:  # Feriados US
            fechas_pago_cupon_habil = [siguiente_dia_habil_us(date) for date in self.fechas_cupon]

        self.fechas_pago_cupon_habil = np.array(fechas_pago_cupon_habil)


        # Dias entre cpn: Agregar la fecha de emisión al inicio de la lista de fechas de cupón
        auxiliar_fechas_cpn_con_emision = [self.emision] + self.fechas_cupon
        aux_fechas_cupon_con_emision_numpy = np.array(auxiliar_fechas_cpn_con_emision)

        # Fechas de periodo de devengamiento de intereses offseteado
        fechas_devengo_intereses_habil = np.array([n_dias_laborales(pd.to_datetime(date),self.dias_lag_indice_desde) for date in aux_fechas_cupon_con_emision_numpy])

        if self.convencion_devengamiento == "Actual":
            dias_entre_cupones = np.diff(aux_fechas_cupon_con_emision_numpy)
            dias_entre_cupones = np.array([delta.days for delta in dias_entre_cupones])
        elif self.convencion_devengamiento == "ISMA-30":
            dias_entre_cupones = np.array([days360(aux_fechas_cupon_con_emision_numpy[i], aux_fechas_cupon_con_emision_numpy[i+1],"EU") for i in range(len(aux_fechas_cupon_con_emision_numpy) - 1)])
        elif self.convencion_devengamiento == "NASD-30":
            dias_entre_cupones = np.array([days360(aux_fechas_cupon_con_emision_numpy[i], aux_fechas_cupon_con_emision_numpy[i+1],"US_NASD") for i in range(len(aux_fechas_cupon_con_emision_numpy) - 1)])

        # Variable para calcular el cupón Dias / dias en el año segun la base
        dias_entre_cupones_anual = dias_entre_cupones / self.convencion_base

        # Valor Residual: cálculo de valores residuales
        amortizacion = self.amortizacion
        self._valor_nominal_adj = self.valor_nominal * self.factor_capitalizacion
        valor_residual_pivot = self.valor_nominal # variable pivot para el list comprehension
        valores_residuales = np.array([valor_residual_pivot := valor_residual_pivot - amort if amort != 0 else valor_residual_pivot for amort in amortizacion[:-1]])
        valores_residuales = np.insert(valores_residuales, 0, self.valor_nominal)
        self.valores_residuales = valores_residuales


        # Cálculo de intereses

        # Cálculo del premio sobre spread en interés variable

        if self.step_up == True:
            self.intereses = data.get("Intereses")
        else:
            if self.tipo_tasa_interes == "FIJA":
                index_premium = [0] * self.cupones
            else:
                # Calcular el promedio de la serie badlar para cada intervalo de fechas de pago (fechas_devengo_intereses_habil tiene 29 incluye emision para promediar)
                index_premium = []
                for i in range(len(fechas_devengo_intereses_habil) - 1):
                    inicio = fechas_devengo_intereses_habil[i]
                    fin = fechas_devengo_intereses_habil[i + 1]
                    promedio = inputs['badlar_proyectado'][(inputs['badlar_proyectado'].index >= inicio) & (inputs['badlar_proyectado'].index < fin)]['BADLAR'].mean() # se puede mejorar a una version donde la proyeccion sea segun el settlement
                    index_premium.append(promedio)

            cupon_aplicable = [tasavar + self.cupon_spread for tasavar in index_premium]

            intereses = dias_entre_cupones_anual * (cupon_aplicable) / 100 * valores_residuales
            self.intereses = intereses



        # Cálculo de paridad



    def generate_cashflows(self, settlement_date=None):
        '''
        Calcula y genera los flujos de caja para un instrumento financiero, considerando
            diferentes tipos de ajustes sobre el capital y las fechas de los cupones y pagos.

        Parámetros:
        - settlement_date (opcional): La fecha de liquidación del instrumento financiero.
        Si no se proporciona, se calcula automáticamente utilizando la función n_dias_laborales.

        Proceso:
        1. Establecimiento de la Fecha de Liquidación:
        - Si settlement_date no se proporciona, se calcula usando n_dias_laborales.
        2. Cálculo de Ajustes Sobre el Capital:
        - Dependiendo de self.ajuste_sobre_capital, se calculan los ajustes aplicables.
            Los tipos pueden incluir 'None', 'CER', 'CER PROYECTADO', 'A3500', 'A3500 PROYECTADO'.
        - Se utilizan distintas estrategias de cálculo para cada tipo de ajuste.
        3. Generación de Flujos de Caja:
        - Se crean y almacenan dos conjuntos de flujos de caja, cf_cpn y cf_pmt, que incluyen
            fechas, intereses, amortización, ajustes y totales.
        - Se filtran para incluir solo aquellos después de self.fecha_settlement.
        - Se crea el valor residual hasta el momento

        Retorna:
        - Imprime y retorna los DataFrames self.cashflow_cpn y self.cashflow_pmt, representando
        los flujos de caja filtrados desde la fecha de liquidación.
        '''
        if settlement_date is None:
            settlement_date = n_dias_laborales(date.today(), self.plazo_habitual_liquidacion)
        else:
            settlement_date = datetime.strptime(settlement_date, '%d/%m/%Y').date()

        self.fecha_settlement = settlement_date
        # Ajustes sobre el capital CER y proyección: none, cer, cer_proyectado, a3500, a3500 proyectado
        if self.ajuste_sobre_capital== None:
            ajuste_aplicable = [1] * self.cupones
        elif self.ajuste_sobre_capital == "CER":
            ajuste_aplicable = []
            # Fechas de ratio offseteado
            fecha_cer_base = n_dias_laborales(pd.to_datetime(self.emision),self.dias_lag_ajuste_base)
            ajuste_base = inputs['cer'].loc[fecha_cer_base, 'CER']
            self.ajuste_base = ajuste_base
            fecha_ajuste_si_no_hay_dato = n_dias_laborales(settlement_date, self.dias_lag_ajuste)
            for i in range(self.cupones):
                fecha_ajuste_actual = n_dias_laborales(self.fechas_cupon[i],self.dias_lag_ajuste)
                ajuste_actual = inputs['cer'].loc[fecha_ajuste_actual, 'CER'] if fecha_ajuste_actual in inputs['cer'].index else inputs['cer'].loc[fecha_ajuste_si_no_hay_dato]['CER']
                ratio_aplicable = ajuste_actual / ajuste_base
                ajuste_aplicable.append(ratio_aplicable)
                        
            self.fecha_cer_base = fecha_cer_base
            self.ajuste_aplicable = ajuste_aplicable

        elif self.ajuste_sobre_capital == "CER PROYECTADO":
            ajuste_aplicable = []
            # Fechas de ratio offseteado
            fecha_cer_base = n_dias_laborales(pd.to_datetime(self.emision),self.dias_lag_ajuste_base)
            ajuste_base = inputs['cer_proyectado'].loc[fecha_cer_base, 'CER']
            self.ajuste_base = ajuste_base
            fecha_ajuste_si_no_hay_dato = n_dias_laborales(settlement_date, self.dias_lag_ajuste)
            for i in range(self.cupones):
                fecha_ajuste_actual = n_dias_laborales(self.fechas_cupon[i],self.dias_lag_ajuste)
                ajuste_actual = inputs['cer_proyectado'].loc[fecha_ajuste_actual, 'CER'] if fecha_ajuste_actual in inputs['cer_proyectado'].index else inputs['cer_proyectado'].loc[fecha_ajuste_si_no_hay_dato]['CER']
                ratio_aplicable = ajuste_actual / ajuste_base
                ajuste_aplicable.append(ratio_aplicable)
                
            self.fecha_cer_base = fecha_cer_base
            self.ajuste_aplicable = ajuste_aplicable

        elif self.ajuste_sobre_capital == "A3500":
            ajuste_aplicable = []
            for i in range(self.cupones):
                fecha_ajuste_actual = n_dias_laborales(self.fechas_cupon[i],self.dias_lag_ajuste)
                ajuste_actual = inputs['a3500'].loc[fecha_ajuste_actual, 'tca3500'] if fecha_ajuste_actual in inputs['a3500'].index else inputs['a3500'].iloc[-1]['tca3500']
                ratio_aplicable = ajuste_actual
                ajuste_aplicable.append(ratio_aplicable)
        elif self.ajuste_sobre_capital == "A3500 PROYECTADO":
            ajuste_aplicable = []
            for i in range(self.cupones):
                fecha_ajuste_actual = n_dias_laborales(self.fechas_cupon[i],self.dias_lag_ajuste)
                ajuste_actual = inputs['a3500_proyectado'].loc[fecha_ajuste_actual, 'tca3500'] if fecha_ajuste_actual in inputs['a3500_proyectado'].index else inputs['a3500_proyectado'].iloc[-1]['tca3500']
                ratio_aplicable = ajuste_actual
                ajuste_aplicable.append(ratio_aplicable)

        self.numero_ajuste_sobre_capital = np.array(ajuste_aplicable) * self.factor_capitalizacion


        cf_cpn = {
            "Fechas": self.fechas_cupon,
            "Intereses": self.intereses,
            "Amortización": self.amortizacion,
            "Ajuste": self.numero_ajuste_sobre_capital,
            "Total": (self.intereses + self.amortizacion)*self.numero_ajuste_sobre_capital / self.valor_nominal
        }
        cf_pmt = {
            "Fechas": self.fechas_pago_cupon_habil,
            "Intereses": self.intereses,
            "Amortización": self.amortizacion,
            "Ajuste": self.numero_ajuste_sobre_capital,
            "Total": (self.intereses + self.amortizacion)*self.numero_ajuste_sobre_capital / self.valor_nominal

        }


        self.cashflow_cpn_full = pd.DataFrame(cf_cpn)
        self.cashflow_pmt_full = pd.DataFrame(cf_pmt)
        self.cashflow_cpn = pd.DataFrame(cf_cpn)[pd.DataFrame(cf_cpn)['Fechas'] > self.fecha_settlement]
        self.cashflow_pmt = pd.DataFrame(cf_pmt)[pd.DataFrame(cf_pmt)['Fechas'] > self.fecha_settlement]

        self.valor_residual = self.valor_nominal - sum(self.cashflow_cpn_full['Amortización'][self.cashflow_cpn_full['Fechas'] <= self.fecha_settlement]) # cada 100 o %

        #return print(self.cashflow_cpn,"\n" ,self.cashflow_pmt)

    def calcula_intereses_corridos(self, settlement_date=None):
        """
        Calcula los intereses corridos del bono desde el último pago de cupón hasta la fecha actual
        o una fecha de liquidación especificada.

        Parámetros:
        - settlement_date (opcional): La fecha hasta la cual se calcularán los intereses corridos.
          Si no se proporciona, se utilizará la fecha actual.

        Retorna:
        - Los intereses corridos del bono.
        """
        self.generate_cashflows(settlement_date)

        fecha_ultimo_cpn = self.emision if self.fecha_settlement <= self.cashflow_cpn_full['Fechas'].min() else self.cashflow_cpn_full['Fechas'][self.cashflow_cpn_full['Fechas'] <= self.fecha_settlement].max()
        fecha_siguiente_cpn = self.cashflow_cpn_full['Fechas'][self.cashflow_cpn_full['Fechas'] > self.fecha_settlement].min()

        # Calcular días transcurridos desde el último pago de cupón según la convención que corresponda
        if self.convencion_devengamiento == "Actual":
            dias_transcurridos = (self.fecha_settlement - fecha_ultimo_cpn).days
        elif self.convencion_devengamiento == "ISMA-30":
            dias_transcurridos = days360(fecha_ultimo_cpn, self.fecha_settlement, 'EU')
        elif self.convencion_devengamiento == "NASD-30":
            dias_transcurridos = days360(fecha_ultimo_cpn, self.fecha_settlement, 'US_NASD')

        # Calcular días entre cupones (no utilizo la frecuencia )
        if self.convencion_devengamiento == "Actual":
            dias_entre_cpn_total = (fecha_siguiente_cpn - fecha_ultimo_cpn).days
        elif self.convencion_devengamiento == "ISMA-30":
            dias_entre_cpn_total = days360(fecha_ultimo_cpn, fecha_siguiente_cpn, 'EU')
        elif self.convencion_devengamiento == "NASD-30":
            dias_entre_cpn_total = days360(fecha_ultimo_cpn, fecha_siguiente_cpn, 'US_NASD')

        # Calcular días remanentes
        if self.cupones == 1:
            dias_remanentes = (fecha_siguiente_cpn - self.fecha_settlement).days
        else:
            if self.convencion_devengamiento == "Actual":
                dias_remanentes = (fecha_siguiente_cpn - self.fecha_settlement).days
            elif self.convencion_devengamiento == "ISMA-30":
                dias_remanentes = days360(self.fecha_settlement, fecha_siguiente_cpn, 'EU')
            elif self.convencion_devengamiento == "NASD-30":
                dias_remanentes = days360(self.fecha_settlement, fecha_siguiente_cpn, 'US_NASD')

        interes_aplicable_corrido = self.cashflow_cpn_full.loc[self.cashflow_cpn_full['Fechas'] == fecha_siguiente_cpn, 'Intereses'].iloc[0]
        ajuste_aplicable_corrido = self.cashflow_cpn_full.loc[self.cashflow_cpn_full['Fechas'] == fecha_siguiente_cpn, 'Ajuste'].iloc[0]

        # Calcular los intereses corridos
        intereses_corridos = interes_aplicable_corrido * (dias_transcurridos / dias_entre_cpn_total) * ajuste_aplicable_corrido * self.factor_capitalizacion / self.valor_nominal  # dias pasados/dias año

        self.intereses_corridos = intereses_corridos
        self.dias_corridos = dias_transcurridos
        self.dias_remanentes = dias_remanentes
        self.ultimo_cupon = fecha_ultimo_cpn
        self.proximo_cupon = fecha_siguiente_cpn
        self._ajuste_aplicable_corrido = ajuste_aplicable_corrido
        self.valor_tecnico = self.valor_residual * (self._ajuste_aplicable_corrido) / self.valor_nominal + self.intereses_corridos / self.factor_capitalizacion


        return intereses_corridos


    def calcula_tirea(self, precio, settlement_date=None):
        """
        Calcula la tasa interna de retorno efectiva anual (TIREA) de un instrumento financiero,
        utilizando el método de Newton-Raphson para encontrar la tasa de descuento que iguala
        el valor presente neto de los flujos de caja al precio dado.

        Parámetros:
        - precio: El precio actual del instrumento financiero.
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
        Si no se proporciona, se calcula automáticamente.

        Proceso:
        1. Validación del Precio:
        - Verifica que el precio proporcionado sea mayor que cero.
        2. Generación de Flujos de Caja:
        - Utiliza el método generate_cashflows para generar los flujos de caja del instrumento.
        3. Preparación de Datos para el Cálculo:
        - Filtra los flujos de caja desde la fecha de liquidación y ajusta con el precio.
        4. Cálculo de la TIREA:
        - Utiliza el método de Newton-Raphson para encontrar la tasa de descuento.
            Incluye el cálculo del valor presente neto y su derivada.
        - Realiza iteraciones hasta alcanzar la precisión deseada o el máximo de iteraciones.
        5. Calcula TNA según convención

        Retorna:
        - La tasa interna de retorno efectiva anual (TIREA) del instrumento financiero.

        Nota:
        - Este método asume una comprensión básica del método de Newton-Raphson,
        más detalles en: https://es.wikipedia.org/wiki/M%C3%A9todo_de_Newton
        """
        self.generate_cashflows(settlement_date)
        self.calcula_intereses_corridos(settlement_date)
        if precio <= 0:
            raise ValueError("No se ingresó un precio válido")
        if self.quote_price_cnv == 'CLEAN':
            self.precio = precio + self.intereses_corridos
            self.precio_clean = precio
        else:
            self.precio = precio
            self.precio_clean = precio - self.intereses_corridos
        # adjunto calculo de paridad
        self.paridad = self.precio / self.valor_tecnico


        cf = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > self.fecha_settlement]
        nueva_fila = {
                        'Fechas': self.fecha_settlement,
                        'Intereses': 0,
                        'Amortización': 0,
                        'Ajuste': 0,
                        'Total': - self.precio
                    }
        cf = pd.concat([pd.DataFrame([nueva_fila]), cf], ignore_index=True)

        # Función del valor presente neto
        def valor_presente(tasa):
            return sum(row['Total'] / (1 + tasa) ** ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf.iterrows())

        # Derivada del valor presente neto
        def derivada_vp(tasa):
            return sum(-row['Total'] * ((row['Fechas'] - self.fecha_settlement).days / 365) / (1 + tasa) ** ((row['Fechas'] - self.fecha_settlement).days / 365 + 1) for index, row in cf.iterrows())

        # Método de Newton-Raphson https://es.wikipedia.org/wiki/M%C3%A9todo_de_Newton (me aproximo usando la pendiente derivada)
        #tasa_actual = 0.5 if self.paridad < 0.5 else (0.01 if self.paridad < 1.20 else (-0.2 if self.paridad < 1.30 else (-0.5 if self.paridad < 1.40 else (-0.6 if self.paridad < 1.70 else (-0.8 if self.paridad < 2 else -0.94)))))
        tasa_actual = (
            0.3755 if 0.2 <= self.paridad < 0.3 else
            0.3255 if 0.3 <= self.paridad < 0.4 else
            0.2754 if 0.4 <= self.paridad < 0.5 else
            0.2253 if 0.5 <= self.paridad < 0.6 else
            0.1947 if 0.6 <= self.paridad < 0.7 else
            0.1391 if 0.7 <= self.paridad < 0.8 else
            0.0835 if 0.8 <= self.paridad < 0.9 else
            0.0501 if 0.9 <= self.paridad < 1.0 else
            -0.1201 if 1.0 <= self.paridad < 1.1 else
            -0.3000 if 1.1 <= self.paridad < 1.2 else
            -0.7000 if 1.2 <= self.paridad < 1.3 else
            -0.7500 if 1.3 <= self.paridad < 1.4 else
            -0.8000 if 1.4 <= self.paridad < 1.5 else
            -0.900000 if 1.5 <= self.paridad < 1.6 else
            -0.95 if 1.6 <= self.paridad < 1.7 else
            -0.99 if 1.7 <= self.paridad < 1.8 else
            -0.999 if 1.8 <= self.paridad < 1.9 else
            -0.9999 if 1.9 <= self.paridad < 2.0 else
            -0.99999 if self.paridad >= 2 else 0.01
            )
        tasa_actual = tasa_actual
        precision = 0.0001
        iteraciones = 0
        max_iteraciones = 10000  # Para evitar bucles infinitos

        while True:
            iteraciones += 1
            vp_actual = valor_presente(tasa_actual)
            derivada_actual = derivada_vp(tasa_actual)
            tasa_nueva = tasa_actual - vp_actual / derivada_actual

            if abs(tasa_nueva - tasa_actual) < precision or iteraciones > max_iteraciones:
                break

            tasa_actual = tasa_nueva

        '''
        # Búsqueda binaria para encontrar la tasa de descuento (esto era re bruto pero efectivo)
        bajo, alto = -20, 20  # Asumiendo que la tasa está entre 0% y 100%
        precision = 0.00001  # Precisión deseada
        tasa_actual = (alto + bajo) / 2

        while alto - bajo > precision:
            vp = vp(tasa_actual)
            if vp > precio_objetivo:
                alto = tasa_actual
            else:
                bajo = tasa_actual
            tasa_actual = (alto + bajo) / 2
        '''

        self.tirea = tasa_actual.real

        # Cálculo TNA según cnv
        if self.cnv_tna == 'plazo remanente':
            dias_al_vto = (self.vencimiento - self.fecha_settlement).days
            self.tna = tir_a_tna(self.tirea,dias_al_vto,self.convencion_base)
        else:
            self.tna = tir_a_tna(self.tirea,self.cnv_tna,self.convencion_base)
        return tasa_actual.real


    def calcula_precio(self, tasa_descuento, settlement_date=None):
        '''
        Calcula el precio de un instrumento financiero utilizando una tasa de descuento dada.
        El precio se calcula como el valor presente de los flujos de caja futuros del instrumento.

        Parámetros:
        - tasa_descuento: La tasa de descuento a utilizar para el cálculo del precio. Siempre TIREA
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
        Si no se proporciona, se calcula automáticamente.

        Proceso:
        1. Generación de Flujos de Caja:
        - Utiliza el método generate_cashflows para generar los flujos de caja del instrumento.
        2. Cálculo del Precio:
        - Calcula el valor presente de los flujos de caja utilizando la tasa de descuento proporcionada.
        - Filtra los flujos de caja desde la fecha de liquidación.

        Retorna:
        - El precio del instrumento financiero, basado en la tasa de descuento dada.
        '''
        # Generar los flujos de caja
        self.generate_cashflows(settlement_date)
        self.calcula_intereses_corridos(settlement_date)

        # Almacena nueva tasa:
        self.tirea = tasa_descuento.real
        # Almacena nueva tasa en versión TNA
        if self.cnv_tna == 'plazo remanente':
            dias_al_vto = (self.vencimiento - self.fecha_settlement).days
            self.tna = tir_a_tna(tasa_descuento.real,dias_al_vto,self.convencion_base)
        else:
            self.tna = tir_a_tna(tasa_descuento.real,self.cnv_tna,self.convencion_base)



        # Filtrar los flujos de caja desde la fecha de liquidación
        cf = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > self.fecha_settlement]

        # Calcular el valor presente de los flujos de caja
        precio = sum(row['Total'] / (1 + tasa_descuento.real) ** ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf.iterrows())

        self.precio = precio
        self.precio_clean = precio - self.intereses_corridos
        # Adjunto cálculo de paridad
        self.paridad = self.precio / self.valor_tecnico

        if self.quote_price_cnv == 'CLEAN':
            show_px = self.precio_clean
        else:
            show_px = self.precio

        return round(show_px, 8)

    def calcula_duration(self, tasa_descuento, settlement_date=None):
        """
        Calcula la duración de un bono utilizando una tasa de descuento dada.
        La duración se calcula como la suma ponderada de los tiempos hasta cada flujo de caja,
        dividida por el precio del bono.

        Parámetros:
        - tasa_descuento: La tasa de descuento a utilizar para el cálculo de la duración. Siempre TIREA
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
            Si no se proporciona, se calcula automáticamente.

        Retorna:
        - La duración del bono, que es una medida del tiempo promedio ponderado hasta la recepción
            de los flujos de caja.
        """
        # Generar los flujos de caja
        self.generate_cashflows(settlement_date)

        # Filtrar los flujos de caja desde la fecha de liquidación
        cf = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > self.fecha_settlement]

        # Calcular el precio del bono
        precio = sum(row['Total'] / (1 + tasa_descuento.real) ** ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf.iterrows())

        # Calcular la duración
        duration = sum((row['Total'] / (1 + tasa_descuento.real) ** ((row['Fechas'] - self.fecha_settlement).days / 365)) * ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf.iterrows()) / precio

        self.duration = duration
        return duration

    def calcula_modified_duration(self, tasa_descuento, settlement_date=None):
        """
        Calcula la duración modificada de un bono utilizando una tasa de descuento dada.
        La duración modificada mide la sensibilidad del precio del bono a los cambios en las tasas de interés.

        Parámetros:
        - tasa_descuento: La tasa de descuento a utilizar para el cálculo de la duración modificada. Siempre TIREA
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
          Si no se proporciona, se calcula automáticamente.

        Retorna:
        - La duración modificada del bono.
        """
        # Primero, calcular la duración de Macaulay
        duracion_macaulay = self.calcula_duration(tasa_descuento.real, settlement_date)

        # Calcular la duración modificada
        modified_duration = duracion_macaulay / (1 + tasa_descuento.real)

        self.modified_duration = modified_duration

        return modified_duration

    def calcula_convexity(self, tasa_descuento, settlement_date=None):
        """
        PD: Revisar en este método la formula, no lo se rick, parece falso. Aunque respeto la fórmula de convexity, tengo que hacer en papel la derivada
        Calcula la convexidad de un bono utilizando una tasa de descuento dada.
        La convexidad es una medida de la sensibilidad de la duración del bono a los cambios en las tasas de interés.

        Parámetros:
        - tasa_descuento: La tasa de descuento a utilizar para el cálculo de la convexidad.
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
          Si no se proporciona, se calcula automáticamente.

        Retorna:
        - La convexidad del bono.
        """
        # Generar los flujos de caja
        self.generate_cashflows(settlement_date)

        # Filtrar los flujos de caja desde la fecha de liquidación
        cf = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > self.fecha_settlement]

        # Calcular el precio del bono
        precio = sum(row['Total'] / (1 + tasa_descuento) ** ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf.iterrows())

        # Calcular la convexidad
        convexidad = sum(row['Total'] * ((row['Fechas'] - self.fecha_settlement).days / 365) ** 2 / ((1 + tasa_descuento) ** ((row['Fechas'] - self.fecha_settlement).days / 365 + 2)) for index, row in cf.iterrows()) / (precio * (1 + tasa_descuento) ** 2)

        self.convexity = convexidad
        return convexidad

    def calcula_total_return(self, tirea_inicial, tirea_final, terminal_date,settlement_date=None):
        # Identificar y sumar los cupones cobrados
        self.generate_cashflows(settlement_date)
        fechas_cpn_cobrados = (self.cashflow_cpn_full['Fechas'] > self.fecha_settlement) & (self.cashflow_cpn_full['Fechas'] <= datetime.strptime(terminal_date, '%d/%m/%Y').date())
        cupones_cobrados = self.cashflow_cpn_full.loc[fechas_cpn_cobrados, 'Total'].sum()

        # Calcula el precio final del bono usando la tirea_final
        cf_final = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > datetime.strptime(terminal_date, '%d/%m/%Y').date()]
        precio_final = sum(row['Total'] / (1 + tirea_final) ** ((row['Fechas'] - datetime.strptime(terminal_date, '%d/%m/%Y').date()).days / 365) for index, row in cf_final.iterrows())


        # Calcula el precio inicial del bono usando la tirea_inicial
        cf_inicial = self.cashflow_cpn[self.cashflow_cpn['Fechas'] > self.fecha_settlement]
        precio_inicial = sum(row['Total'] / (1 + tirea_inicial) ** ((row['Fechas'] - self.fecha_settlement).days / 365) for index, row in cf_inicial.iterrows())

        # precio_inicial = self.calcula_precio(tasa_descuento=tirea_inicial, settlement_date=settlement_date)

        # Calcular ganancia/pérdida de capital
        ganancia_capital = precio_final - precio_inicial


        # Calcular el total return
        total_return = (ganancia_capital + cupones_cobrados) / precio_inicial
        inverse_pnl = (1 / (1+total_return))- 1

        # Formatear 'total_return' como un porcentaje con 6 decimales
        total_return_formatted = "{:.6%}".format(total_return)
        inverse_pnl_formatted = "{:.6%}".format(inverse_pnl)


        trdf = pd.DataFrame({
        'Fecha Inicial': [self.fecha_settlement.strftime("%d/%m/%Y")],
        'Fecha Terminal': [terminal_date],
        'Px inicial': [precio_inicial],
        'Px final': [precio_final],
        'P&L Capital': [ganancia_capital],
        'Cupones Cobrados': [cupones_cobrados],
        'Total Return': [total_return_formatted],
        'Inverse P&L': [inverse_pnl_formatted]

            })

        trdf_vertical = trdf.transpose()
        trdf_vertical.columns = ['Total Return Valores']

        return trdf_vertical

    def genera_ticket(self, precio_ticket, nominales_ticket=1000000, settlement_date=None):
        """
        Método para generar el ticket

        Parámetros:
        - precio_ticket: El precio según convención
        - nominales_ticket: nominales según convención. Int
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
          Si no se proporciona, se calcula automáticamente.

        Retorna:
        - ticket
        """
        # Calcula interés corrido y tir
        self.calcula_tirea(precio_ticket, settlement_date)
        self.calcula_intereses_corridos(settlement_date)

        # Tasa aplicable si es variable:
        badlar_aplicable = inputs['badlar'].tail(5)["BADLAR"].mean()

        if self.cnv_tna == 'plazo remanente': # verifica si A no es regular con frecuencias 2,4,6,12,48,365
            cnv_dias_al_vto = (self.vencimiento - self.fecha_settlement).days
        else:
            cnv_dias_al_vto = self.cnv_tna 

        if self.tipo_tasa_interes == "VARIABLE":
            ticket = {
                    'Nombre': self.codigo,
                    'Fecha Liquidación': self.fecha_settlement,
                    'Precio': self.precio,
                    'VN ticket': int(nominales_ticket),
                    'Monto Total': nominales_ticket * self.precio,
                    'Principal': nominales_ticket * self.precio_clean,
                    'Interés': nominales_ticket * self.intereses_corridos,
                    'Días Devengados': self.dias_corridos,
                    'TIREA': self.tirea,
                    'TNA': self.tna,
                    'Tasa Aplicable': f'{self.index} {badlar_aplicable}%',
                    'Margen TNA':  self.tna - badlar_aplicable/100,
                    'Convención TNA': f'{int(cnv_dias_al_vto)}/{int(self.convencion_base)}',
                    'Callable': f'{self.callable}'
                    }
        else:
            ticket = {
                    'Nombre': self.codigo,
                    'Fecha Liquidación': self.fecha_settlement,
                    'Precio': self.precio,
                    'VN ticket': int(nominales_ticket),
                    'Monto Total': nominales_ticket * self.precio,
                    'Principal': nominales_ticket * self.precio_clean,
                    'Interés': nominales_ticket * self.intereses_corridos,
                    'Días Devengados': self.dias_corridos,
                    'TIREA': self.tirea,
                    'TNA': self.tna,
                    'Convención TNA': f'{int(cnv_dias_al_vto)}/{int(self.convencion_base)}',
                    'Callable': f'{self.callable}'
                   }

        ticket_pd = pd.DataFrame([ticket])
        ticket_pd_vertical = ticket_pd.transpose()
        ticket_pd_vertical.columns = ['Valores']

        # formateo Vertical
        # Formateo para Monto Total, Principal e Interés
        ticket_pd_vertical.loc['VN ticket', 'Valores'] = "{:,.2f}".format(ticket_pd_vertical.loc['VN ticket', 'Valores']).replace(",", "X").replace(".", ",").replace("X", ".")
        ticket_pd_vertical.loc['Monto Total', 'Valores'] = "{:,.2f}".format(ticket_pd_vertical.loc['Monto Total', 'Valores']).replace(",", "X").replace(".", ",").replace("X", ".")
        ticket_pd_vertical.loc['Principal', 'Valores'] = "{:,.2f}".format(ticket_pd_vertical.loc['Principal', 'Valores']).replace(",", "X").replace(".", ",").replace("X", ".")
        ticket_pd_vertical.loc['Interés', 'Valores'] = "{:,.2f}".format(ticket_pd_vertical.loc['Interés', 'Valores']).replace(",", "X").replace(".", ",").replace("X", ".")

        # Formateo para TIREA y TNA como porcentajes
        ticket_pd_vertical.loc['TIREA', 'Valores'] = "{:.4%}".format(ticket_pd_vertical.loc['TIREA', 'Valores'])
        ticket_pd_vertical.loc['TNA', 'Valores'] = "{:.4%}".format(ticket_pd_vertical.loc['TNA', 'Valores'])
        if self.tipo_tasa_interes == "VARIABLE":
            ticket_pd_vertical.loc['Margen TNA', 'Valores'] = "{:.2%}".format(ticket_pd_vertical.loc['Margen TNA', 'Valores'])

        self.ultimo_ticket = ticket_pd_vertical


        return ticket_pd_vertical

    def genera_ticket_blotter(self, fondo, operacion, contraparte, precio_ticket, nominales_ticket=1000000, settlement_date=None):
        """
        Método para generar el ticket

        Parámetros:
        - precio_ticket: El precio según convención
        - nominales_ticket: nominales según convención. Int
        - settlement_date (opcional): La fecha de liquidación para el cálculo de los flujos de caja.
          Si no se proporciona, se calcula automáticamente.

        Retorna:
        - ticket
        """
        # Calcula interés corrido y tir
        self.calcula_tirea(precio_ticket, settlement_date)
        self.calcula_intereses_corridos(settlement_date)

        fondos_cnv = {
            "Acciones": 505,
            "Ahorro": 506,
            "Ahorro Plus": 606,
            "Cohen Pesos": 583,
            "Crecimiento": 722,
            "CRF DOL": 1025,
            "FEDERAL I": 605,
            "Gestion I": 624,
            "Gestion II": 625,
            "Gestion III": 749,
            "Gestion IV": 533,
            "Gestion IX": 1089,
            "Gestion Pyme": 1263,
            "Gestion V": 815,
            "Gestión VI": 816,
            "Gestion VII": 962,
            "Gestion VIII": 963,
            "Gestion X": 1090,
            "Gestion XI": 1228,
            "Internacional": 532,
            "Latinoamerica": 504,
            "Moneda": 534,
            "Multimercado I": 607,
            "MULTIMERCADO II": 998,
            "Patrimonio I": 996,
            "Performance": 748,
            "Pesos": 536,
            "PLUS": 616,
            "Pyme": 589,
            "PYMES": 598,
            "Recursos": 535,
            "Renta": 503,
            "Renta Dolares": 849,
            "DOLARES PLUS": 997,
            "Select": 531
        }

        # Función para obtener el número CNV basado en el nombre del fondo
        def obtener_cnv(fondo):
            return fondos_cnv.get(fondo, "Fondo no encontrado")


        ticket = {
            'Fecha': date.today().strftime("%d/%m/%Y"),
            'Fondo': fondo,
            'CNV': obtener_cnv(fondo),
            'Operacion': operacion,
            'Contraparte': contraparte,
            'Codigo': self.codigo,
            'VN': "{:,.0f}".format(int(nominales_ticket)),
            'Plazo': (self.fecha_settlement - datetime.today().date()).days,
            'Moneda ': self.moneda,
            'Precio Full': self.precio,
            'Producido': "{:,.2f}".format(nominales_ticket * self.precio).replace(",", "X").replace(".", ",").replace("X", "."),
            'Tasa Referencia': {"TIR":"{:.2f}%".format(self.tirea * 100),"TNA":"{:.2f}%".format(self.tna * 100),"Cnv TNA": f'{int(self.cnv_tna)}/{int(self.convencion_base)}'},
            'Fecha Liquidación': self.fecha_settlement.strftime("%d/%m/%Y"),
            'Monto Total': "{:,.2f}".format(nominales_ticket * self.precio),
            'Principal': "{:,.2f}".format(nominales_ticket * self.precio_clean),
            'Interés': nominales_ticket * self.intereses_corridos,
            'Días Devengados': self.dias_corridos,
        }
        ticket_pd = pd.DataFrame([ticket])

        return ticket_pd



# %%
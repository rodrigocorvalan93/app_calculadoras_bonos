# OMS: Calculadora de Bonos & Analytics

Dashboard interactivo para el análisis de renta fija, monitoreo de mercado en tiempo real y gestión de órdenes (Order Management System), enfocado principalmente en el mercado argentino.



## 🚀 Componentes Principales

El proyecto está estructurado de forma modular para facilitar el mantenimiento y la escalabilidad:

* **`OMSweb_app.py`**: El punto de entrada de la aplicación. Gestiona la interfaz de usuario con **Streamlit**, coordinando la visualización de curvas, tablas de monitoreo y el feed de noticias.
* **`bymaapi.py`**: El motor de datos. Se encarga de la conexión con las APIs de mercado para obtener precios, puntas de compra/venta y volúmenes en tiempo real.
* **`OMSnews.py`**: Módulo de noticias asíncrono para el seguimiento de novedades financieras locales y globales.
* **`OMScredit.py` & `OMSprices.py`**: Lógica de cálculo para scoring crediticio, valuación de bonos y análisis de tasas (TNA, TIR, MD).

## 🛠️ Instalación y Configuración

Para levantar el entorno localmente, se recomienda utilizar un entorno virtual de Python:

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/rodrigocorvalan93/app_calculadoras_bonos.git](https://github.com/rodrigocorvalan93/app_calculadoras_bonos.git)
    cd app_calculadoras_bonos
    ```

2.  **Crear y activar entorno virtual:**
    ```bash
    python -m venv venv
    # En Windows:
    .\venv\Scripts\activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar credenciales:**
    Asegúrate de tener los archivos de configuración local (que están en el `.gitignore`) con tus credenciales de API para que `bymaapi.py` pueda conectar correctamente.

## 📈 Uso

Para ejecutar la aplicación de Streamlit:

```bash
streamlit run OMSweb_app.py

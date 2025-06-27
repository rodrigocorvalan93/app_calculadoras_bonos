import tkinter as tk
import random

def generar_color_aleatorio():
  """Genera un color hexadecimal aleatorio."""
  return f'#{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}'

def realizar_sorteo(participantes, ventana, etiqueta_resultado):
  """Realiza un sorteo aleatorio y muestra el ganador en la ventana.

  Args:
    participantes: Una lista de nombres de los participantes.
    ventana: La ventana principal de Tkinter.
    etiqueta_resultado: El widget Label donde se mostrará el resultado.
  """
  if not participantes:
    etiqueta_resultado.config(text="La lista está vacía.", fg="red")
  else:
    ganador = random.choice(participantes)
    color_ganador = generar_color_aleatorio()
    etiqueta_resultado.config(text=f"¡El ganador es: {ganador}!", fg=color_ganador, font=("Arial", 16, "bold"))
    ventana.config(bg=generar_color_aleatorio()) # Cambia el fondo al anunciar el ganador

def iniciar_sorteo():
  """Obtiene los participantes del campo de texto y realiza el sorteo."""
  nombres = entrada_participantes.get()
  lista_participantes = [nombre.strip() for nombre in nombres.split(',') if nombre.strip()]
  realizar_sorteo(lista_participantes, ventana, resultado_label)

def abrir_ventana_sorteo():
  """Crea y abre la ventana de sorteo con elementos interactivos."""
  global ventana, entrada_participantes, resultado_label # Hacerlas variables globales para accederlas en funciones

  ventana = tk.Tk()
  ventana.title("Sorteo Aleatorio")
  ventana.geometry("400x300") # Establecer un tamaño inicial
  ventana.config(bg=generar_color_aleatorio())

  # Etiqueta para instrucciones
  instrucciones = tk.Label(ventana, text="Ingrese los participantes separados por comas:", font=("Arial", 10), bg=ventana['bg'])
  instrucciones.pack(pady=10)

  # Campo de entrada para los participantes
  entrada_participantes = tk.Entry(ventana, width=30)
  entrada_participantes.pack(pady=5)

  # Botón para iniciar el sorteo
  boton_sortear = tk.Button(ventana, text="¡Sortear!", command=iniciar_sorteo, font=("Arial", 12, "bold"), bg="lightblue")
  boton_sortear.pack(pady=15)

  # Etiqueta para mostrar el resultado
  resultado_label = tk.Label(ventana, text="", font=("Arial", 14), bg=ventana['bg'])
  resultado_label.pack(pady=10)

  ventana.mainloop()

if __name__ == "__main__":
  abrir_ventana_sorteo()
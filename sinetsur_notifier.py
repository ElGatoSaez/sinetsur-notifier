import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SINETSUR_URL  = os.getenv("SINETSUR_URL")
SINETSUR_USER = os.getenv("SINETSUR_USER")
SINETSUR_PASS = os.getenv("SINETSUR_PASS")

def login():
    session = requests.Session()
    # Primer GET para obtener los campos ocultos del formulario
    resp = session.get(SINETSUR_URL, timeout=30)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    payload = {}
    # Capturamos los campos ocultos típicos en ASP.NET
    for field in ["__VIEWSTATE", "__EVENTVALIDATION", "__VIEWSTATEGENERATOR"]:
        tag = soup.find('input', {'name': field})
        if tag:
            payload[field] = tag.get('value', '')
    
    # Campos de login
    payload['ctl00$ContentPlaceHolder1$txtNombreUsuario'] = SINETSUR_USER
    payload['ctl00$ContentPlaceHolder1$txtPass'] = SINETSUR_PASS
    # Simulamos el click en el botón de login (tipo image)
    payload['ctl00$ContentPlaceHolder1$btnEntrar.x'] = '50'
    payload['ctl00$ContentPlaceHolder1$btnEntrar.y'] = '10'
    
    login_resp = session.post(SINETSUR_URL, data=payload, timeout=30)
    return session, login_resp.text

def extraer_pacientes(html, ya_vistos):
    """
    Extrae pacientes nuevos (filas con clase rgRow o rgAltRow) que tengan en la octava columna
    el subelemento con texto "PED" o cuyo atributo title contenga "PEDIATRIA".
    Se usa la primera columna (ej. RUT) como identificador único.
    """
    soup = BeautifulSoup(html, 'html.parser')
    nuevos = []

    # Verificamos que el servicio esté en Infantil
    unidad_input = soup.find('input', {'id': 'ctl00_ContentPlaceHolder1_RadToolBar1_i0_cbxUnidades_Input'})
    if not unidad_input:
        print("No se encontró el input de la unidad.")
        return nuevos
    valor_unidad = unidad_input.get('value', '').strip().upper()
    if valor_unidad != "INFANTIL":
        print("¡Atención! El servicio no está en INFANTIL, se encuentra en:", valor_unidad)
        print("HTML del input:")
        print(unidad_input.prettify())
    
    # Verificamos que la pestaña "Categorizados" esté activa
    tab = soup.find('a', class_="rtsLink rtsSelected")
    if not tab or "Categorizados" not in tab.get_text():
        print("La pestaña 'Categorizados' no está activa.")
        return nuevos

    # Ubicamos la tabla de pacientes
    grid_div = soup.find('div', {'id': 'ctl00_ContentPlaceHolder1_dgv_categorizados_GridData'})
    if not grid_div:
        print("No se encontró el grid de pacientes.")
        return nuevos

    table = grid_div.find('table')
    if not table:
        print("No se encontró la tabla de pacientes.")
        return nuevos

    tbody = table.find('tbody')
    if not tbody:
        print("No se encontró el cuerpo de la tabla.")
        return nuevos

    # Recorremos cada fila (tr) que tenga clase rgRow o rgAltRow
    rows = tbody.find_all('tr', class_=lambda x: x and ("rgRow" in x or "rgAltRow" in x))
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 8:
            continue
        
        # La octava columna (índice 7) debe contener un <span> con texto "PED" o title "PEDIATRIA"
        subunidad_cell = cols[7]
        span = subunidad_cell.find('span')
        if not span:
            continue
        subunidad_text = span.get_text(strip=True).upper()
        subunidad_title = span.get('title', '').upper()
        if subunidad_text != "PED" and "PEDIATRIA" not in subunidad_title:
            continue

        # Usamos la primera columna (por ejemplo, el RUT) como identificador único
        paciente_id = cols[0].get_text(strip=True)
        if paciente_id in ya_vistos:
            continue

        # Extraemos el contenido de cada columna (el texto de <label> o el texto directo)
        datos = []
        for col in cols:
            label = col.find('label')
            if label:
                datos.append(label.get_text(strip=True))
            else:
                datos.append(col.get_text(strip=True))
        nuevos.append((paciente_id, datos))
        ya_vistos.add(paciente_id)
    return nuevos

def guardar_log(html):
    """Guarda el HTML en un archivo cuyo nombre incluye el timestamp actual."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"log{timestamp}.html"
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML guardado en", log_filename)

def main():
    ya_vistos = set()
    print("Iniciando polling: en cada ciclo se vuelve a loguear y se extraen los pacientes nuevos...")
    
    while True:
        try:
            # Se realiza el login en cada iteración para mantener la sesión activa
            session, html = login()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Imprime el usuario logueado (según el contenido del h4)
            h4 = soup.find('h4', {'id': 'ContentPlaceHolder1_txtNombreUsuario'})
            if h4:
                usuario = h4.get_text(strip=True)
                print("Usuario logueado:", usuario)
            else:
                print("No se encontró el h4 con el usuario logueado.")
            
            # Guarda el HTML en un log (para depuración)
            #guardar_log(html)
            
            # Verifica el input de unidad
            unidad_input = soup.find('input', {'id': 'ctl00_ContentPlaceHolder1_RadToolBar1_i0_cbxUnidades_Input'})
            if unidad_input:
                valor_unidad = unidad_input.get('value', '').strip().upper()
                print("Valor del input de unidad:", valor_unidad)
                if valor_unidad != "INFANTIL":
                    print("¡Atención! El servicio no está en INFANTIL, se encuentra en:", valor_unidad)
                    print("HTML del input:")
                    print(unidad_input.prettify())
            else:
                print("No se encontró el input de la unidad.")
            
            # Extrae los pacientes nuevos de subunidad PED
            nuevos = extraer_pacientes(html, ya_vistos)
            if nuevos:
                for paciente_id, datos in nuevos:
                    print("Paciente ID:", paciente_id)
                    print("Datos:", " | ".join(datos))
                    print("-" * 50)
            else:
                print("No hay nuevos pacientes de subunidad PED.")
        except Exception as e:
            print("Error en polling:", e)
        # Espera 60 segundos antes de la siguiente iteración (se volverá a loguear)
        time.sleep(60)

if __name__ == "__main__":
    main()

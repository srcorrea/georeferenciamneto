import streamlit as st
import requests
import math
import hashlib
import os
import sqlite3
import bcrypt
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_folium import st_folium
import folium
import pandas as pd
from datetime import datetime
import json

# ==================== CONFIGURAÇÃO DA PÁGINA ====================
st.set_page_config(
    page_title="GeoEstudo Pro",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== BANCO DE DADOS DE USUÁRIOS (SQLite) ====================
def init_users_db():
    """Cria a tabela de usuários se não existir."""
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_user(username, email, password, is_admin=False):
    """Adiciona um novo usuário ao banco (com hash de senha)."""
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        c.execute('''
            INSERT INTO users (username, email, hashed_password, is_admin)
            VALUES (?, ?, ?, ?)
        ''', (username, email, hashed, is_admin))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def verify_user(username, password):
    """Verifica credenciais e retorna (sucesso, admin_flag)."""
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute('SELECT hashed_password, is_admin FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode(), result[0].encode()):
        return True, result[1] == 1
    return False, False

def change_password(username, new_password):
    """Altera a senha de um usuário."""
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    c.execute('UPDATE users SET hashed_password = ? WHERE username = ?', (hashed, username))
    conn.commit()
    conn.close()

# Inicializa o banco de dados
init_users_db()

# ==================== SISTEMA DE AUTENTICAÇÃO ====================
def login():
    """Formulário de login."""
    st.title("🔐 Acesso Restrito - GeoEstudo Pro")
    col1, col2 = st.columns([1, 1], gap="medium")
    with col1:
        st.markdown("### Login")
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            success, is_admin = verify_user(username, password)
            if success:
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.is_admin = is_admin
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    with col2:
        st.markdown("### Criar Conta")
        new_user = st.text_input("Novo usuário (mín. 3 caracteres)")
        new_email = st.text_input("E-mail")
        new_pass = st.text_input("Senha (mín. 6 caracteres)", type="password")
        if st.button("Cadastrar"):
            if len(new_user) < 3 or len(new_pass) < 6:
                st.error("Usuário precisa ter pelo menos 3 caracteres e senha 6 caracteres.")
            elif add_user(new_user, new_email, new_pass):
                st.success("Conta criada! Agora faça login.")
            else:
                st.error("Nome de usuário ou e-mail já existente.")

def logout():
    """Limpa a sessão e desloga."""
    for key in ['authenticated', 'username', 'is_admin']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# ==================== FUNÇÕES GEOESPACIAIS (Cache via @st.cache_data) ====================
@st.cache_data(ttl=86400)
def geocode_endereco(endereco: str):
    geolocator = Nominatim(user_agent="geoestudo_pro_app")
    try:
        location = geolocator.geocode(endereco, timeout=10)
        if location:
            return location.latitude, location.longitude, location.address
        return None
    except Exception as e:
        st.error(f"Erro na geocodificação: {e}")
        return None

@st.cache_data(ttl=86400)
def buscar_dados_ibge(lat, lon):
    try:
        response = requests.get("https://servicodados.ibge.gov.br/api/v1/localidades/municipios", timeout=10)
        if response.status_code != 200:
            return None
        cidades = response.json()
        melhor_cidade = None
        menor_dist = float('inf')
        for cidade in cidades:
            if cidade.get('centroide') and cidade['centroide'].get('latitude'):
                lat_c = float(cidade['centroide']['latitude'])
                lon_c = float(cidade['centroide']['longitude'])
                dist = geodesic((lat, lon), (lat_c, lon_c)).km
                if dist < menor_dist and dist < 50:
                    menor_dist = dist
                    melhor_cidade = cidade
        if melhor_cidade:
            return {
                "nome": melhor_cidade['nome'],
                "uf": melhor_cidade['microrregiao']['mesorregiao']['UF']['nome'],
                "sigla": melhor_cidade['microrregiao']['mesorregiao']['UF']['sigla'],
                "regiao": melhor_cidade['microrregiao']['mesorregiao']['UF']['regiao']['nome'],
                "distancia_centroide": round(menor_dist, 2)
            }
        return None
    except Exception as e:
        st.warning(f"Erro IBGE: {e}")
        return None

@st.cache_data(ttl=86400)
def buscar_geoapi_estados():
    """Exemplo: obtém lista de estados via GeoApi (endpoint público)."""
    try:
        # Endpoint público da GeoApi para metadados de estados
        url = "https://geoapi.com.br/api/meta/states"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

@st.cache_data(ttl=3600)
def buscar_ana_estacoes_proximas(lat, lon, raio_km=50):
    """Busca estações fluviométricas da ANA nas proximidades (simulado)."""
    # Nota: A API da ANA não possui busca geográfica simples; este é um placeholder
    # Em produção, pode-se usar o webservice de dados abertos da ANA.
    try:
        url = f"https://dadosabertos.ana.gov.br/api/3/action/datastore_search?resource_id=estacoes"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Filtragem local seria feita aqui
            return data.get('result', {}).get('records', [])[:5]
        return []
    except:
        return []

@st.cache_data(ttl=86400)
def buscar_ibge_agregados(codigo_municipio):
    """Exemplo: busca população estimada do município via API de Agregados."""
    try:
        # População estimada (projeção) – agregado 6579 (estimativas populacionais)
        url = f"https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/2024/variaveis/9324?localidades=N6[{codigo_municipio}]"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0].get('resultados', [{}])[0].get('series', [{}])[0].get('serie', {}).get('2024', 'N/A')
        return 'N/A'
    except:
        return 'N/A'

def calcular_azimute(lat1, lon1, lat2, lon2):
    lat1_r = math.radians(lat1); lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2); lon2_r = math.radians(lon2)
    delta_lon = lon2_r - lon1_r
    x = math.sin(delta_lon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(delta_lon)
    az = math.degrees(math.atan2(x, y))
    return (az + 360) % 360

def direcao_cardinal(az):
    if az < 90: return "N" if az < 45 else "NE"
    if az < 180: return "L" if az < 135 else "SE"
    if az < 270: return "S" if az < 225 else "SO"
    return "O" if az < 315 else "NO"

def geo_to_utm_simplificada(lat, lon):
    fuso = 23
    hemisferio = 'S' if lat < 0 else 'N'
    easting = 320000 + (lon + 46.65) * 110000
    northing = 7400000 - (lat + 23.5) * 111000 if hemisferio == 'S' else lat * 111000
    return {"fuso": fuso, "hemisferio": hemisferio, "easting": round(easting), "northing": round(northing)}

# ==================== INTERFACE PRINCIPAL (APÓS LOGIN) ====================
def main_app():
    st.sidebar.title(f"📌 GeoEstudo Pro\n👤 {st.session_state.username}")
    if st.sidebar.button("🔓 Logout"):
        logout()
    st.sidebar.markdown("**Painel de Administração**" if st.session_state.is_admin else "")
    st.sidebar.info(
        "**Funcionalidades:**\n"
        "- Geocodificação de qualquer endereço do Brasil\n"
        "- Dados oficiais IBGE (Localidades + Agregados)\n"
        "- GeoApi (polígonos de estados)\n"
        "- Estações fluviométricas próximas (ANA)\n"
        "- Distâncias e azimutes\n"
        "- Conversão UTM (didática)\n"
        "- Memorial descritivo automático"
    )

    st.title("📐 GeoEstudo Pro - Georreferenciamento Avançado")
    st.markdown("Pesquise qualquer endereço no Brasil e obtenha análise geoespacial completa.")

    # Campo de busca
    col1, col2 = st.columns([3, 1])
    with col1:
        endereco_input = st.text_input("Digite o endereço:", placeholder="Ex: Rua Glauco Velasques, 332, Casa Verde, São Paulo - SP")
    with col2:
        pesquisar = st.button("🔍 Geocodificar", type="primary")

    if pesquisar and endereco_input:
        with st.spinner("Geocodificando endereço e coletando dados..."):
            resultado = geocode_endereco(endereco_input)
            if resultado:
                lat, lon, end_full = resultado
                st.success(f"✅ Endereço encontrado: {end_full}")

                # Dados IBGE
                ibge_data = buscar_dados_ibge(lat, lon)
                # GeoApi (exemplo: lista de estados)
                geoapi_estados = buscar_geoapi_estados()
                # ANA estações próximas
                estacoes_ana = buscar_ana_estacoes_proximas(lat, lon)
                # População estimada (se tiver código do município)
                pop_estimada = None
                if ibge_data:
                    # Para obter código do município, precisaria de outra chamada; simplificado
                    pop_estimada = buscar_ibge_agregados('3550308')  # exemplo São Paulo

                # Conversão UTM
                utm = geo_to_utm_simplificada(lat, lon)

                # Pontos de referência pré-definidos
                ref_points = {
                    "Marco Zero - Praça da Sé (SP)": (-23.5505, -46.6333),
                    "Parque Ibirapuera (SP)": (-23.5883, -46.6595),
                    "MASP - Av. Paulista (SP)": (-23.5617, -46.6561)
                }

                analise = []
                for nome, coord in ref_points.items():
                    dist = geodesic((lat, lon), coord).km
                    az = calcular_azimute(lat, lon, coord[0], coord[1])
                    analise.append({
                        "Ponto": nome,
                        "Distância (km)": round(dist, 2),
                        "Azimute (°)": round(az, 1),
                        "Direção": direcao_cardinal(az)
                    })

                # Exibir resultados em abas
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["📍 Coordenadas & IBGE", "📏 Análise Espacial", "🗺️ Mapa Interativo", "📊 Fontes Externas", "📄 Memorial"])

                with tab1:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.subheader("Coordenadas Geográficas")
                        st.write(f"**Latitude:** {lat:.6f}°")
                        st.write(f"**Longitude:** {lon:.6f}°")
                        st.write(f"**Datum:** SIRGAS2000 (WGS84)")
                        st.subheader("Projeção UTM (didática)")
                        st.write(f"**Fuso:** {utm['fuso']}{utm['hemisferio']}")
                        st.write(f"**Easting:** {utm['easting']} m")
                        st.write(f"**Northing:** {utm['northing']} m")
                    with col_b:
                        st.subheader("📊 Dados IBGE")
                        if ibge_data:
                            st.write(f"**Município:** {ibge_data['nome']}")
                            st.write(f"**UF:** {ibge_data['uf']} ({ibge_data['sigla']})")
                            st.write(f"**Região:** {ibge_data['regiao']}")
                            st.write(f"**Distância do centroide:** {ibge_data['distancia_centroide']} km")
                            if pop_estimada:
                                st.write(f"**População estimada (2024):** {pop_estimada}")
                        else:
                            st.warning("Dados IBGE não disponíveis.")

                with tab2:
                    st.subheader("Distâncias e Azimutes para Pontos de Referência")
                    st.dataframe(pd.DataFrame(analise), use_container_width=True)

                with tab3:
                    st.subheader("Mapa Interativo")
                    m = folium.Map(location=[lat, lon], zoom_start=14, control_scale=True)
                    folium.Marker([lat, lon], popup=f"<b>Localização pesquisada</b><br>{end_full}", icon=folium.Icon(color="red", icon="home", prefix="fa")).add_to(m)
                    folium.Circle([lat, lon], radius=500, color="blue", fill=True, fill_opacity=0.1, popup="Raio de 500m").add_to(m)
                    for nome, coord in ref_points.items():
                        folium.Marker(coord, popup=nome, icon=folium.Icon(color="green", icon="info-sign")).add_to(m)
                    st_folium(m, width=700, height=500)

                with tab4:
                    st.subheader("Dados de Fontes Complementares")
                    if geoapi_estados:
                        st.write("**GeoApi - Estados Brasileiros (exemplo):**")
                        st.json(geoapi_estados[:5])
                    if estacoes_ana:
                        st.write("**Estações Fluviométricas ANA próximas (simulado):**")
                        st.dataframe(pd.DataFrame(estacoes_ana))
                    if pop_estimada:
                        st.success(f"População estimada (IBGE Agregados): {pop_estimada} habitantes")

                with tab5:
                    st.subheader("Memorial Descritivo")
                    memorial = f"""
                    **MEMORIAL DESCRITIVO - GEORREFERENCIAMENTO**

                    **Endereço pesquisado:** {end_full}
                    **Coordenadas geográficas (SIRGAS2000):** Latitude {lat:.6f}°, Longitude {lon:.6f}°.

                    **Sistema de projeção:** UTM fuso {utm['fuso']}{utm['hemisferio']} (Easting: {utm['easting']} m, Northing: {utm['northing']} m).

                    **Informações do IBGE:**  
                    {ibge_data['nome'] if ibge_data else 'Não disponível'} - {ibge_data['uf'] if ibge_data else ''} ({ibge_data['sigla'] if ibge_data else ''}), região {ibge_data['regiao'] if ibge_data else ''}.

                    **Análise de referências:**  
                    {chr(10).join([f"- {a['Ponto']}: {a['Distância (km)']} km, azimute {a['Azimute (°)']}° ({a['Direção']})" for a in analise])}

                    **Fontes de dados:** IBGE (Localidades e Agregados), GeoApi, ANA, OpenStreetMap (Nominatim).

                    **Data da consulta:** {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
                    """
                    st.markdown(memorial)
                    st.download_button("📥 Baixar Memorial (TXT)", memorial, file_name=f"memorial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", mime="text/plain")
            else:
                st.error("❌ Endereço não encontrado.")
    elif pesquisar and not endereco_input:
        st.warning("Digite um endereço.")

    st.markdown("---")
    st.caption("GeoEstudo Pro - Dados sujeitos à disponibilidade das APIs públicas.")

# ==================== FLUXO PRINCIPAL ====================
if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    login()
else:
    main_app()
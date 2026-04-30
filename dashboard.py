import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# Configuración
import os
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}'
}

def fetch(tabla, params=''):
    r = requests.get(f'{SUPABASE_URL}/rest/v1/{tabla}?{params}', headers=HEADERS)
    return r.json()

# Página
st.set_page_config(page_title='Dashboard Visitas', page_icon='🍷', layout='wide')
st.title('🍷 Dashboard de Visitas — Traversa & Noble Alianza')

# Cargar datos
visitas_raw = fetch('visitas', 'select=id,created_at,actividad,nombre_atendente,notas,lat,lng,precision_metros,agentes(nombre),pdvs(nombre,lat,lng)&order=created_at.desc')
fotos_raw = fetch('fotos', 'select=visita_id,url&limit=1000&order=visita_id.asc')
prods_raw = fetch('visita_productos', 'select=visita_id,unidades_gondola,stock_deposito,productos(nombre)&limit=1000&order=visita_id.asc')
if not visitas_raw or isinstance(visitas_raw, dict):
    st.warning('No hay visitas registradas todavía.')
    st.stop()

# Armar dataframe
rows = []
for v in visitas_raw:
    rows.append({
        'id': v['id'],
        'fecha': (pd.Timestamp(v['created_at']).tz_convert('America/Sao_Paulo')).strftime('%Y-%m-%d'),
        'hora': (pd.Timestamp(v['created_at']).tz_convert('America/Sao_Paulo')).strftime('%H:%M'),
        'agente': v['agentes']['nombre'] if v.get('agentes') else '-',
        'pdv': v['pdvs']['nombre'] if v.get('pdvs') else '-',
        'actividad': v.get('actividad', '-'),
        'atendente': v.get('nombre_atendente', '-'),
        'notas': v.get('notas', ''),
        'lat': v.get('lat'),
        'lng': v.get('lng'),
        'precision': v.get('precision_metros'),
        'pdv_lat': v['pdvs']['lat'] if v.get('pdvs') else None,
        'pdv_lng': v['pdvs']['lng'] if v.get('pdvs') else None,
    })

df = pd.DataFrame(rows)

# Calcular distancia GPS
def distancia_metros(row):
    if None in [row['lat'], row['lng'], row['pdv_lat'], row['pdv_lng']]:
        return None
    import math
    dlat = float(row['lat']) - float(row['pdv_lat'])
    dlng = (float(row['lng']) - float(row['pdv_lng'])) * math.cos(math.radians(float(row['lat'])))
    return round(111000 * math.sqrt(dlat**2 + dlng**2))

df['distancia_m'] = df.apply(distancia_metros, axis=1)

# ── MÉTRICAS ──────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric('Total visitas', len(df))
col2.metric('PDVs visitados', df['pdv'].nunique())
col3.metric('Agentes activos', df['agente'].nunique())
alertas = df[df['distancia_m'] > 500].shape[0]
col4.metric('⚠️ Alertas GPS', alertas)

st.divider()

# ── FILTROS ───────────────────────────────────────────────
col_a, col_b, col_c = st.columns(3)
with col_a:
    agentes_lista = ['Todos'] + sorted(df['agente'].unique().tolist())
    agente_sel = st.selectbox('Agente', agentes_lista)
with col_b:
    pdv_lista = ['Todos'] + sorted(df['pdv'].unique().tolist())
    pdv_sel = st.selectbox('PDV', pdv_lista)
with col_c:
    solo_alertas = st.checkbox('Solo alertas GPS (>500m)')

# Aplicar filtros
dff = df.copy()
if agente_sel != 'Todos':
    dff = dff[dff['agente'] == agente_sel]
if pdv_sel != 'Todos':
    dff = dff[dff['pdv'] == pdv_sel]
if solo_alertas:
    dff = dff[dff['distancia_m'] > 500]

st.divider()

# ── MAPA ──────────────────────────────────────────────────
st.subheader('🗺️ Mapa de visitas')

mapa = folium.Map(location=[-23.56, -46.66], zoom_start=11)

for _, row in dff.iterrows():
    if row['lat'] and row['lng']:
        dist = row['distancia_m']
        color = 'red' if dist and dist > 500 else 'green'
        popup = f"""
        <b>{row['pdv']}</b><br>
        Agente: {row['agente']}<br>
        Fecha: {row['fecha']} {row['hora']}<br>
        Distancia: {dist}m<br>
        Atendente: {row['atendente']}
        """
        folium.CircleMarker(
            location=[float(row['lat']), float(row['lng'])],
            radius=8,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(popup, max_width=200)
        ).add_to(mapa)

st_folium(mapa, width='100%', height=450)

st.divider()

# ── TABLA DE VISITAS ──────────────────────────────────────
st.subheader('📋 Visitas')

def color_distancia(val):
    if val is None:
        return ''
    return 'background-color: #ffcccc' if val > 500 else 'background-color: #ccffcc'

tabla = dff[['fecha', 'hora', 'agente', 'pdv', 'actividad', 'atendente', 'distancia_m', 'precision', 'notas']].copy()
tabla.columns = ['Fecha', 'Hora', 'Agente', 'PDV', 'Actividad', 'Atendente', 'Distancia (m)', 'Precisión GPS', 'Notas']

st.dataframe(
    tabla.style.applymap(color_distancia, subset=['Distancia (m)']),
    use_container_width=True,
    hide_index=True
)

st.divider()

# ── DETALLE DE VISITA ─────────────────────────────────────
st.subheader('🔍 Detalle de visita')

visita_sel = st.selectbox(
    'Seleccioná una visita',
    options=dff['id'].tolist(),
    index=0,
    format_func=lambda x: f"{dff[dff['id']==x]['fecha'].values[0]} {dff[dff['id']==x]['hora'].values[0]} — {dff[dff['id']==x]['agente'].values[0]} — {dff[dff['id']==x]['pdv'].values[0]}"
)

if visita_sel:
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.markdown('**Productos en góndola**')
        prods_visita = [p for p in prods_raw if str(p['visita_id']) == str(visita_sel)]
        if prods_visita:
            for p in prods_visita:
                nombre = p['productos']['nombre']
                unidades = p.get('unidades_gondola', 0)
                stock = '✅ Sí' if p.get('stock_deposito') else '❌ No'
                st.write(f"**{nombre}** — {unidades} uds en góndola — Stock: {stock}")
        else:
            st.write('Sin datos de productos')

    with col_der:
        st.markdown('**Fotos**')
        fotos_visita = [f for f in fotos_raw if str(f['visita_id']) == str(visita_sel)]
        if fotos_visita:
            cols = st.columns(min(len(fotos_visita), 3))
            for i, foto in enumerate(fotos_visita):
                cols[i % 3].image(foto['url'], use_container_width=True)
        else:
            st.write('Sin fotos')
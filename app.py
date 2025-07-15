# app.py

import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import Counter

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(layout="wide")

try:
    CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
    auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    # Check-up de autenticação
    sp.artist('06HL4z0CvFAxyc27GXpf02') # ID da banda Queen
except Exception as e:
    st.error("🚨 Falha na autenticação com o Spotify!")
    st.warning("Verifique suas credenciais no Streamlit Cloud Secrets e faça o 'Reboot app'.")
    st.stop()

# --- FUNÇÕES AUXILIARES ---
def obter_generos_validos(_sp):
    """Busca e retorna a lista de gêneros válidos para recomendações."""
    try:
        return _sp.recommendation_genre_seeds()['genres']
    except:
        return []

def buscar_album(nome_album):
    """Busca um álbum no Spotify e retorna um dicionário com seus dados."""
    if not nome_album: return None
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=5)
    if resultados['albums']['items']:
        return resultados['albums']['items']
    return None

# --- INICIALIZAÇÃO DA MEMÓRIA (SESSION STATE) ---
if 'selecoes' not in st.session_state:
    st.session_state['selecoes'] = {'a': [None]*5, 'b': [None]*5}
if 'busca' not in st.session_state:
    st.session_state['busca'] = {}

# --- FUNÇÕES DE CALLBACK ---
def selecionar_album(lado, indice, album_data):
    st.session_state.selecoes[lado][indice] = album_data
    st.session_state.busca[f'{lado}{indice}'] = []

def remover_album(lado, indice):
    st.session_state.selecoes[lado][indice] = None

# --- INTERFACE GRÁFICA (UI) ---
st.title("🎵 Dueto")
st.write("Descubra novas músicas com seus amigos ou parceiro(a)!")

col1, col2 = st.columns(2)
for lado, coluna in [('a', col1), ('b', col2)]:
    with coluna:
        st.header(f"Lado {lado.upper()}")
        for i in range(5):
            st.divider()
            album_selecionado = st.session_state.selecoes[lado][i]
            slot_key = f'{lado}{i}'
            if album_selecionado:
                col_img, col_btn = st.columns([1, 2])
                with col_img:
                    st.image(album_selecionado['capa'], use_container_width=True)
                with col_btn:
                    st.write(f"**{album_selecionado['nome']}**")
                    st.caption(album_selecionado['artista'])
                    st.button("Remover", key=f"rem_{slot_key}", on_click=remover_album, args=(lado, i))
            else:
                query = st.text_input("Buscar por nome do álbum", key=f"query_{slot_key}")
                if query:
                    st.session_state.busca[slot_key] = buscar_album(query)
                
                if slot_key in st.session_state.busca and st.session_state.busca[slot_key]:
                    st.write("Resultados da busca:")
                    for res in st.session_state.busca[slot_key]:
                        album_data = {"id": res['id'], "nome": res['name'], "artista": res['artists'][0]['name'], "capa": res['images'][0]['url']}
                        res_col_img, res_col_info, res_col_btn = st.columns([1,2,1])
                        with res_col_img: st.image(album_data['capa'])
                        with res_col_info:
                            st.write(f"**{album_data['nome']}**")
                            st.caption(album_data['artista'])
                        with res_col_btn:
                            st.button("Selecionar", key=f"sel_{slot_key}_{album_data['id']}", on_click=selecionar_album, args=(lado, i, album_data))
st.divider()

# --- BOTÃO DE ANÁLISE FINAL ---
analisar_btn = st.button("Analisar Dueto", type="primary", use_container_width=True)

if analisar_btn:
    dados_albuns_a = [album for album in st.session_state.selecoes['a'] if album]
    dados_albuns_b = [album for album in st.session_state.selecoes['b'] if album]
    
    if not dados_albuns_a or not dados_albuns_b:
        st.warning("É preciso selecionar pelo menos um álbum para cada lado.")
    else:
        with st.spinner("Analisando seus gostos, buscando candidatos e calculando a sintonia... 🎶"):
            # --- FASE 1: COLETA DE INGREDIENTES ---
            generos_validos = obter_generos_validos(sp)
            gostos_de_genero = []
            artistas_fonte_ids = set()
            albuns_selecionados_ids = {album['id'] for album in dados_albuns_a + dados_albuns_b}

            for album_data in dados_albuns_a + dados_albuns_b:
                try:
                    album_info_completo = sp.album(album_data['id'])
                    info_artista = sp.artist(album_info_completo['artists'][0]['id'])
                    artistas_fonte_ids.add(info_artista['id'])
                    for genero in info_artista['genres']:
                        if genero in generos_validos:
                            gostos_de_genero.append(genero)
                except: pass

            # --- FASE 2: GERAÇÃO DE CANDIDATOS (LÓGICA DE SEMENTES DINÂMICA) ---
            
            # Constrói as sementes de forma segura
            sementes_artistas = list(artistas_fonte_ids)[:3]
            top_generos = [genre for genre, count in Counter(gostos_de_genero).most_common(5)]
            sementes_generos = []
            slots_restantes_genero = 5 - len(sementes_artistas)
            
            for genero in top_generos:
                if len(sementes_generos) < slots_restantes_genero:
                    sementes_generos.append(genero)
                else:
                    break

            # Verificação final e definitiva antes da chamada
            if not sementes_artistas and not sementes_generos:
                st.error("Não foi possível extrair informações suficientes dos álbuns selecionados para gerar recomendações.")
                st.stop()
            
            # ---- MUDANÇA CRÍTICA: Construção dinâmica dos parâmetros ----
            params = {'limit': 50}
            if sementes_artistas:
                params['seed_artists'] = sementes_artistas
            if sementes_generos:
                params['seed_genres'] = sementes_generos

            st.info("Informações para Depuração:")
            st.write("Parâmetros Finais Enviados para a API:", params)
            
            try:
                # Chama a API com os parâmetros construídos dinamicamente
                recomendacoes_api = sp.recommendations(**params)
            except Exception as e:
                st.error("Ocorreu um erro ao buscar recomendações do Spotify. Tente uma combinação diferente de álbuns.")
                st.stop()


            # --- FASE 3 e 4 (Sem alterações) ---
            candidatos_pontuados = []
            artistas_processados = {}
            for faixa in recomendacoes_api['tracks']:
                album_candidato = faixa['album']
                if album_candidato['id'] in albuns_selecionados_ids or any(c['album_data']['id'] == album_candidato['id'] for c in candidatos_pontuados):
                    continue
                score = 0
                id_artista_candidato = album_candidato['artists'][0]['id']
                if id_artista_candidato not in artistas_processados:
                    try: artistas_processados[id_artista_candidato] = sp.artist(id_artista_candidato)['genres']
                    except: artistas_processados[id_artista_candidato] = []
                generos_candidato = artistas_processados[id_artista_candidato]
                for genero in generos_candidato:
                    if genero in gostos_de_genero: score += 10
                if id_artista_candidato in artistas_fonte_ids: score += 5
                candidatos_pontuados.append({
                    "album_data": {"id": album_candidato['id'], "nome": album_candidato['name'], "artista": album_candidato['artists'][0]['name'], "capa": album_candidato['images'][0]['url']},
                    "score": score,
                    "popularity": faixa.get('popularity', 0)
                })

            if not candidatos_pontuados:
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
            else:
                candidatos_ordenados = sorted(candidatos_pontuados, key=lambda x: (x['score'], x['popularity']), reverse=True)
                top_5_recomendacoes = candidatos_ordenados[:5]
                st.success("Análise Concluída!")
                st.divider()
                st.subheader("✨ Top 5 Recomendações para o Dueto ✨")
                st.write("A primeira recomendação é a que tem mais sintonia com o gosto do dueto!")
                for i, rec in enumerate(top_5_recomendacoes):
                    album = rec['album_data']
                    col_img, col_info = st.columns([1, 4])
                    with col_img: st.image(album['capa'], use_container_width=True)
                    with col_info:
                        st.write(f"**{i+1}. {album['nome']}**")
                        st.write(f"Artista: {album['artista']}")
                    st.divider()
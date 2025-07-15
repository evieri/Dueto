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
    sp.artist('06HL4z0CvFAxyc27GXpf02') # Check-up
except Exception as e:
    st.error("🚨 Falha na autenticação com o Spotify!")
    st.warning("Verifique suas credenciais no Streamlit Cloud Secrets e faça o 'Reboot app'.")
    st.stop()

# --- FUNÇÕES AUXILIARES ---
def obter_generos_validos(_sp):
    try: return _sp.recommendation_genre_seeds()['genres']
    except: return []

def buscar_album(nome_album):
    if not nome_album: return None
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=5)
    return resultados['albums']['items'] if resultados['albums']['items'] else None

# --- SESSION STATE E CALLBACKS ---
if 'selecoes' not in st.session_state:
    st.session_state['selecoes'] = {'a': [None]*5, 'b': [None]*5}
if 'busca' not in st.session_state:
    st.session_state['busca'] = {}

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
                with col_img: st.image(album_selecionado['capa'], use_container_width=True)
                with col_btn:
                    st.write(f"**{album_selecionado['nome']}**")
                    st.caption(album_selecionado['artista'])
                    st.button("Remover", key=f"rem_{slot_key}", on_click=remover_album, args=(lado, i))
            else:
                query = st.text_input("Buscar por nome do álbum", key=f"query_{slot_key}")
                if query: st.session_state.busca[slot_key] = buscar_album(query)
                if slot_key in st.session_state.busca and st.session_state.busca[slot_key]:
                    for res in st.session_state.busca[slot_key]:
                        album_data = {"id": res['id'], "nome": res['name'], "artista": res['artists'][0]['name'], "capa": res['images'][0]['url']}
                        res_col_img, res_col_info, res_col_btn = st.columns([1,2,1])
                        with res_col_img: st.image(album_data['capa'], width=100)
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
        with st.spinner("Analisando..."):
            # --- FASE 1: COLETA DE INGREDIENTES ---
            generos_validos = obter_generos_validos(sp)
            gostos_de_genero = []
            artistas_fonte_ids = set()
            albuns_selecionados_ids = {album['id'] for album in dados_albuns_a + dados_albuns_b}

            for album_data in dados_albuns_a + dados_albuns_b:
                try:
                    info_artista = sp.artist(sp.album(album_data['id'])['artists'][0]['id'])
                    artistas_fonte_ids.add(info_artista['id'])
                    for genero in info_artista['genres']:
                        if genero in generos_validos: gostos_de_genero.append(genero)
                except: pass

            # --- FASE 2: GERAÇÃO DE CANDIDATOS COM PLANO A E PLANO B ---
            recomendacoes_api = None
            
            # PLANO A: Tenta com artistas e gêneros
            sementes_artistas = list(artistas_fonte_ids)[:3]
            top_generos = [g for g, c in Counter(gostos_de_genero).most_common(2)]
            
            params_a = {'limit': 25}
            if sementes_artistas: params_a['seed_artists'] = sementes_artistas
            if top_generos: params_a['seed_genres'] = top_generos

            try:
                if 'seed_artists' in params_a or 'seed_genres' in params_a:
                    recomendacoes_api = sp.recommendations(**params_a)
            except Exception:
                recomendacoes_api = None # Falhou, prepara para o Plano B

            # PLANO B: Se o Plano A falhou, tenta com as faixas dos álbuns
            if not recomendacoes_api or not recomendacoes_api.get('tracks'):
                st.info("Plano A falhou. Tentando Plano B com os álbuns como semente...")
                try:
                    # Usa os IDs dos álbuns como sementes de faixas (a API pega a primeira faixa de cada)
                    params_b = {'limit': 25, 'seed_tracks': list(albuns_selecionados_ids)[:5]}
                    recomendacoes_api = sp.recommendations(**params_b)
                except Exception as e:
                    st.error("Ocorreu um erro ao buscar recomendações do Spotify, mesmo no Plano B. Tente uma combinação diferente de álbuns.")
                    st.stop()
            
            # --- FASE 3 E 4 (PONTUAÇÃO E EXIBIÇÃO) ---
            if not recomendacoes_api or not recomendacoes_api.get('tracks'):
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
                st.stop()
            
            candidatos_pontuados = []
            artistas_processados = {}
            for faixa in recomendacoes_api['tracks']:
                album_candidato = faixa['album']
                if album_candidato['id'] in albuns_selecionados_ids or any(c['album_data']['id'] == album_candidato['id'] for c in candidatos_pontuados): continue
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
                    "popularity": faixa.get('popularity', 0)})

            candidatos_ordenados = sorted(candidatos_pontuados, key=lambda x: (x['score'], x['popularity']), reverse=True)
            top_5_recomendacoes = candidatos_ordenados[:5]

            st.success("Análise Concluída!")
            st.divider()
            st.subheader("✨ Top 5 Recomendações para o Dueto ✨")
            for i, rec in enumerate(top_5_recomendacoes):
                album = rec['album_data']
                col_img, col_info = st.columns([1, 4])
                with col_img: st.image(album['capa'], use_container_width=True)
                with col_info:
                    st.write(f"**{i+1}. {album['nome']}**")
                    st.write(f"Artista: {album['artista']}")
                st.divider()
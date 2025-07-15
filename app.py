import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

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

# --- INICIALIZAÇÃO DA MEMÓRIA (SESSION STATE) ---
# Isso só roda uma vez, na primeira vez que o usuário abre a página.
if 'selecoes' not in st.session_state:
    # Criamos uma estrutura para guardar os 5 álbuns de cada lado.
    # 'None' significa que o slot está vazio.
    st.session_state['selecoes'] = {
        'a': [None, None, None, None, None],
        'b': [None, None, None, None, None]
    }
if 'busca' not in st.session_state:
    st.session_state['busca'] = {} # Para guardar os resultados da busca de cada slot


# --- FUNÇÕES DE CALLBACK (Ações dos botões) ---
def selecionar_album(lado, indice, album_data):
    """Callback para quando o botão 'Selecionar' é clicado."""
    st.session_state.selecoes[lado][indice] = album_data
    # Limpa os resultados da busca para este slot
    st.session_state.busca[f'{lado}{indice}'] = []

def remover_album(lado, indice):
    """Callback para quando o botão 'Remover' é clicado."""
    st.session_state.selecoes[lado][indice] = None


# --- INTERFACE GRÁFICA (UI) ---
st.title("🎵 Dueto")
st.write("Descubra novas músicas com seus amigos ou parceiro(a)!")

col1, col2 = st.columns(2)

for lado, coluna in [('a', col1), ('b', col2)]:
    with coluna:
        st.header(f"Lado {lado.upper()}")
        # Loop para criar os 5 slots de seleção de álbum
        for i in range(5):
            st.divider()
            album_selecionado = st.session_state.selecoes[lado][i]
            slot_key = f'{lado}{i}' # Chave única para cada slot (ex: 'a0', 'a1', 'b0'...)

            # Se um álbum já foi selecionado neste slot, mostre-o.
            if album_selecionado:
                col_img, col_btn = st.columns([1, 2])
                with col_img:
                    st.image(album_selecionado['capa'], use_container_width=True)
                with col_btn:
                    st.write(f"**{album_selecionado['nome']}**")
                    st.caption(album_selecionado['artista'])
                    st.button("Remover", key=f"rem_{slot_key}", on_click=remover_album, args=(lado, i))
            
            # Se o slot está vazio, mostre a interface de busca.
            else:
                query = st.text_input("Buscar por nome do álbum", key=f"query_{slot_key}")
                if query:
                    resultados = sp.search(q=f"album:{query}", type="album", limit=5)['albums']['items']
                    st.session_state.busca[slot_key] = resultados
                
                # Mostra os resultados da busca
                if slot_key in st.session_state.busca and st.session_state.busca[slot_key]:
                    st.write("Resultados da busca:")
                    for res in st.session_state.busca[slot_key]:
                        album_data = {
                            "id": res['id'],
                            "nome": res['name'],
                            "artista": res['artists'][0]['name'],
                            "capa": res['images'][0]['url']
                        }
                        
                        res_col_img, res_col_info, res_col_btn = st.columns([1,2,1])
                        with res_col_img:
                            st.image(album_data['capa'])
                        with res_col_info:
                            st.write(f"**{album_data['nome']}**")
                            st.caption(album_data['artista'])
                        with res_col_btn:
                            st.button("Selecionar", key=f"sel_{slot_key}_{album_data['id']}", on_click=selecionar_album, args=(lado, i, album_data))
                
st.divider()

# app.py (cole isso no final do seu arquivo, substituindo o botão e o if existentes)

from collections import Counter

# --- BOTÃO DE ANÁLISE FINAL ---
analisar_btn = st.button("Analisar Dueto", type="primary", use_container_width=True)

if analisar_btn:
    # Coleta os dados diretamente da memória (session_state)
    dados_albuns_a = [album for album in st.session_state.selecoes['a'] if album]
    dados_albuns_b = [album for album in st.session_state.selecoes['b'] if album]
    
    # Validação para garantir que há pelo menos um álbum em cada lado
    if not dados_albuns_a or not dados_albuns_b:
        st.warning("É preciso selecionar pelo menos um álbum para cada lado.")
    else:
        with st.spinner("Analisando seus gostos, buscando candidatos e calculando a sintonia... 🎶"):
            
            # --- FASE 1: COLETA DE INGREDIENTES ---
            gostos_de_genero = []
            artistas_fonte_ids = set()
            albuns_selecionados_ids = {album['id'] for album in dados_albuns_a + dados_albuns_b}

            for album_data in dados_albuns_a + dados_albuns_b:
                try:
                    info_artista = sp.artist(sp.album(album_data['id'])['artists'][0]['id'])
                    artistas_fonte_ids.add(info_artista['id'])
                    gostos_de_genero.extend(info_artista['genres'])
                except Exception as e:
                    pass # Ignora erros de álbuns específicos

            # --- FASE 2: GERAÇÃO DE CANDIDATOS ---
            if not artistas_fonte_ids and not gostos_de_genero:
                st.error("Não foi possível extrair informações suficientes dos álbuns selecionados.")
                st.stop()
            
            # Pega os 2 gêneros mais comuns e 3 artistas para usar como sementes
            top_generos = [genre for genre, count in Counter(gostos_de_genero).most_common(2)]
            
            recomendacoes_api = sp.recommendations(
                seed_artists=list(artistas_fonte_ids)[:3],
                seed_genres=top_generos,
                limit=50 # Pega 50 candidatos para ter uma boa piscina de análise
            )

            # --- FASE 3: SISTEMA DE PONTUAÇÃO ---
            candidatos_pontuados = []
            artistas_processados = {} # Cache simples para evitar chamadas repetidas de API

            for faixa in recomendacoes_api['tracks']:
                album_candidato = faixa['album']

                # Pula se o álbum já foi selecionado pelo usuário
                if album_candidato['id'] in albuns_selecionados_ids:
                    continue
                
                # Pula se o álbum já foi adicionado à lista (evita duplicatas)
                if any(c['album_data']['id'] == album_candidato['id'] for c in candidatos_pontuados):
                    continue

                score = 0
                id_artista_candidato = album_candidato['artists'][0]['id']

                # Cache para os gêneros do artista
                if id_artista_candidato not in artistas_processados:
                    try:
                        artistas_processados[id_artista_candidato] = sp.artist(id_artista_candidato)['genres']
                    except Exception as e:
                        artistas_processados[id_artista_candidato] = []
                
                generos_candidato = artistas_processados[id_artista_candidato]

                # Pontuação por Gênero (+10 por cada match)
                for genero in generos_candidato:
                    if genero in gostos_de_genero:
                        score += 10

                # Pontuação por Artista (+5 se for um artista já selecionado)
                if id_artista_candidato in artistas_fonte_ids:
                    score += 5

                candidatos_pontuados.append({
                    "album_data": {
                        "id": album_candidato['id'],
                        "nome": album_candidato['name'],
                        "artista": album_candidato['artists'][0]['name'],
                        "capa": album_candidato['images'][0]['url']
                    },
                    "score": score,
                    "popularity": album_candidato.get('popularity', 0)
                })

            # --- FASE 4: CLASSIFICAÇÃO FINAL ---
            if not candidatos_pontuados:
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
            else:
                # Ordena por score (maior primeiro) e depois por popularidade (maior primeiro)
                candidatos_ordenados = sorted(
                    candidatos_pontuados, 
                    key=lambda x: (x['score'], x['popularity']), 
                    reverse=True
                )
                
                top_5_recomendacoes = candidatos_ordenados[:5]

                st.success("Análise Concluída!")
                st.divider()
                st.subheader("✨ Top 5 Recomendações para o Dueto ✨")
                st.write("A primeira recomendação é a que tem mais sintonia com o gosto do dueto!")

                for i, rec in enumerate(top_5_recomendacoes):
                    album = rec['album_data']
                    col_img, col_info = st.columns([1, 4])
                    with col_img:
                        st.image(album['capa'], use_container_width=True)
                    with col_info:
                        st.write(f"**{i+1}. {album['nome']}**")
                        st.write(f"Artista: {album['artista']}")
                        # Descomente a linha abaixo se quiser ver a pontuação para debug
                        # st.caption(f"Pontuação de Sintonia: {rec['score']} | Popularidade: {rec['popularity']}")
                    st.divider()
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
    
    # Check-up de autenticação mais detalhado
    test_artist = sp.artist('06HL4z0CvFAxyc27GXpf02') # ID da banda Queen
    st.success(f"✅ Autenticação bem-sucedida! Testado com: {test_artist['name']}")
    
    # Testa se o endpoint de recomendações está funcionando
    try:
        test_rec = sp.recommendations(seed_genres=['pop'], limit=1)
        st.success("✅ Endpoint de recomendações funcionando!")
    except Exception as rec_error:
        st.error(f"❌ Problema com endpoint de recomendações: {rec_error}")
        st.info("💡 Isso pode indicar um problema com as credenciais ou região.")
        
except Exception as e:
    st.error("🚨 Falha na autenticação com o Spotify!")
    st.error(f"Erro detalhado: {e}")
    st.warning("Verifique suas credenciais no Streamlit Cloud Secrets e faça o 'Reboot app'.")
    st.stop()

# --- FUNÇÕES AUXILIARES ---
def obter_generos_validos(_sp):
    """Busca e retorna a lista de gêneros válidos para recomendações."""
    try:
        resultado = _sp.recommendation_genre_seeds()
        st.success(f"✅ Gêneros válidos obtidos da API: {len(resultado['genres'])} gêneros")
        return resultado['genres']
    except Exception as e:
        st.warning(f"⚠️ Erro ao buscar gêneros válidos da API: {e}")
        st.info("🔄 Usando lista de fallback...")
        # Fallback com gêneros conhecidos do Spotify
        fallback_genres = ['pop', 'rock', 'hip-hop', 'jazz', 'classical', 'country', 'electronic', 'folk', 'funk', 'gospel', 'indie', 'latin', 'metal', 'punk', 'reggae', 'soul', 'world-music', 'alternative', 'blues', 'dance', 'house', 'techno', 'ambient', 'drum-and-bass', 'dubstep', 'edm', 'garage', 'hardstyle', 'trance', 'acoustic', 'afrobeat', 'alt-rock', 'british', 'chill', 'disco', 'grunge', 'indie-pop', 'new-age', 'post-dubstep', 'progressive-house', 'r-n-b', 'reggaeton', 'songwriter', 'synth-pop']
        return fallback_genres

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
                    artista_id = album_info_completo['artists'][0]['id']
                    info_artista = sp.artist(artista_id)
                    
                    # Verifica se o artista ID é válido
                    if info_artista and info_artista.get('id'):
                        artistas_fonte_ids.add(info_artista['id'])
                        
                        # Processa gêneros
                        for genero in info_artista.get('genres', []):
                            if genero in generos_validos:
                                gostos_de_genero.append(genero)
                    else:
                        st.warning(f"Artista inválido encontrado no álbum {album_data['nome']}")
                        
                except Exception as e:
                    st.warning(f"Erro ao processar álbum {album_data['nome']}: {e}")
                    continue

            # --- FASE 2: GERAÇÃO DE CANDIDATOS (LÓGICA DE SEMENTES CORRIGIDA) ---
            
            # Converte IDs de artistas para lista e limita a 2 (para deixar espaço para gêneros)
            sementes_artistas = list(artistas_fonte_ids)[:2]
            
            # Conta os gêneros e pega os top 2 que são válidos
            top_generos = [genre for genre, count in Counter(gostos_de_genero).most_common(2)]
            
            # Se não temos gêneros dos artistas, usa gêneros populares
            if not top_generos and generos_validos:
                generos_fallback = ['pop', 'rock', 'indie', 'electronic', 'hip-hop']
                for genero in generos_fallback:
                    if genero in generos_validos:
                        top_generos.append(genero)
                        if len(top_generos) >= 2:
                            break
            
            # Garante que temos pelo menos uma seed
            if not sementes_artistas and not top_generos:
                st.error("Não foi possível extrair informações suficientes dos álbuns selecionados para gerar recomendações.")
                st.stop()
            
            # Constrói os parâmetros seguindo as regras da API
            params = {
                'limit': 50,
                'market': 'BR'  # Especifica o mercado brasileiro
            }
            
            # Adiciona seeds de artistas se houver (máximo 2)
            if sementes_artistas:
                params['seed_artists'] = sementes_artistas
            
            # Adiciona seeds de gêneros se houver (máximo 3)
            if top_generos:
                params['seed_genres'] = top_generos[:3]
            
            # Garantia: sempre ter pelo menos uma seed
            if not params.get('seed_artists') and not params.get('seed_genres'):
                # Última tentativa: usar apenas gêneros populares
                if generos_validos:
                    params['seed_genres'] = [generos_validos[0]]
                else:
                    st.error("Não foi possível obter gêneros válidos da API do Spotify.")
                    st.stop()
            
            st.info("Informações para Depuração:")
            st.write("Artistas encontrados:", len(artistas_fonte_ids))
            st.write("Gêneros encontrados nos seus álbuns:", gostos_de_genero)
            st.write("Gêneros válidos da API (primeiros 10):", generos_validos[:10])
            st.write("Parâmetros Finais Enviados para a API:", params)
            
            try:
                # Testa primeiro com uma chamada simples
                test_params = {'seed_genres': ['pop'], 'limit': 1}
                test_call = sp.recommendations(**test_params)
                
                # Se o teste passou, faz a chamada real
                recomendacoes_api = sp.recommendations(**params)
                st.success(f"API chamada com sucesso! Recebidas {len(recomendacoes_api['tracks'])} recomendações.")
                
            except Exception as e:
                st.error(f"Ocorreu um erro ao buscar recomendações do Spotify: {str(e)}")
                
                # Tenta diagnóstico mais detalhado
                st.write("🔍 **Diagnóstico detalhado:**")
                
                # Testa cada artista individualmente
                artistas_validos = []
                for artista_id in params.get('seed_artists', []):
                    try:
                        artista_info = sp.artist(artista_id)
                        artistas_validos.append(artista_id)
                        st.write(f"✅ Artista {artista_info['name']} (ID: {artista_id}) - OK")
                    except Exception as artist_error:
                        st.write(f"❌ Artista ID {artista_id} - Erro: {artist_error}")
                
                # Tenta apenas com gêneros se os artistas falharam
                if artistas_validos and params.get('seed_genres'):
                    st.write("🔄 **Tentando apenas com gêneros...**")
                    try:
                        params_generos = {'seed_genres': params['seed_genres'], 'limit': 50}
                        recomendacoes_api = sp.recommendations(**params_generos)
                        st.success(f"Sucesso apenas com gêneros! Recebidas {len(recomendacoes_api['tracks'])} recomendações.")
                    except Exception as genre_error:
                        st.error(f"Erro também com gêneros: {genre_error}")
                        st.stop()
                else:
                    st.write("Detalhes do erro para debug:")
                    st.write(f"- Artistas seeds: {params.get('seed_artists', 'Nenhum')}")
                    st.write(f"- Gêneros seeds: {params.get('seed_genres', 'Nenhum')}")
                    st.write("Tente uma combinação diferente de álbuns.")
                    st.stop()

            # --- FASE 3 e 4: PONTUAÇÃO E ORDENAÇÃO ---
            candidatos_pontuados = []
            artistas_processados = {}
            
            for faixa in recomendacoes_api['tracks']:
                album_candidato = faixa['album']
                
                # Pula álbuns já selecionados ou já processados
                if album_candidato['id'] in albuns_selecionados_ids or any(c['album_data']['id'] == album_candidato['id'] for c in candidatos_pontuados):
                    continue
                
                score = 0
                id_artista_candidato = album_candidato['artists'][0]['id']
                
                # Busca gêneros do artista (com cache)
                if id_artista_candidato not in artistas_processados:
                    try: 
                        artistas_processados[id_artista_candidato] = sp.artist(id_artista_candidato)['genres']
                    except: 
                        artistas_processados[id_artista_candidato] = []
                
                generos_candidato = artistas_processados[id_artista_candidato]
                
                # Pontuação por gênero em comum
                for genero in generos_candidato:
                    if genero in gostos_de_genero: 
                        score += 10
                
                # Pontuação por artista conhecido
                if id_artista_candidato in artistas_fonte_ids: 
                    score += 5
                
                candidatos_pontuados.append({
                    "album_data": {
                        "id": album_candidato['id'], 
                        "nome": album_candidato['name'], 
                        "artista": album_candidato['artists'][0]['name'], 
                        "capa": album_candidato['images'][0]['url'] if album_candidato['images'] else ""
                    },
                    "score": score,
                    "popularity": faixa.get('popularity', 0)
                })

            if not candidatos_pontuados:
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
            else:
                # Ordena por score e popularidade
                candidatos_ordenados = sorted(candidatos_pontuados, key=lambda x: (x['score'], x['popularity']), reverse=True)
                top_5_recomendacoes = candidatos_ordenados[:5]
                
                st.success("Análise Concluída!")
                st.divider()
                st.subheader("✨ Top 5 Recomendações para o Dueto ✨")
                st.write("A primeira recomendação é a que tem mais sintonia com o gosto do dueto!")
                
                for i, rec in enumerate(top_5_recomendacoes):
                    album = rec['album_data']
                    col_img, col_info = st.columns([1, 4])
                    with col_img: 
                        if album['capa']:
                            st.image(album['capa'], use_container_width=True)
                    with col_info:
                        st.write(f"**{i+1}. {album['nome']}**")
                        st.write(f"Artista: {album['artista']}")
                        st.caption(f"Score: {rec['score']} | Popularidade: {rec['popularity']}")
                    st.divider()
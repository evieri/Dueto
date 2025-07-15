# app.py

import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---

# Configura o layout da página para ser mais largo
st.set_page_config(layout="wide")

# Carrega as credenciais do arquivo secrets.toml de forma segura
try:
    CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]

    auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # CHECK-UP DE AUTENTICAÇÃO:
    # Tenta buscar um artista conhecido para validar a conexão logo no início.
    sp.artist('06HL4z0CvFAxyc27GXpf02') # ID da banda Queen

except Exception as e:
    st.error("🚨 Falha na autenticação com o Spotify!")
    st.warning("Verifique se as variáveis `SPOTIPY_CLIENT_ID` e `SPOTIPY_CLIENT_SECRET` estão configuradas corretamente nos seus Secrets do Streamlit Cloud.")
    # A linha abaixo ajuda no debug mostrando o erro exato que ocorreu
    # st.exception(e)
    st.stop()


# --- FUNÇÕES AUXILIARES ---

def obter_generos_validos(_sp):
    """Busca e retorna a lista de gêneros válidos para recomendações."""
    return _sp.recommendation_genre_seeds()['genres']

def buscar_album(nome_album):
    """Busca um álbum no Spotify e retorna um dicionário com seus dados."""
    if not nome_album:
        return None
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=1)
    if resultados['albums']['items']:
        album = resultados['albums']['items'][0]
        return {"id": album['id'], "nome": album['name'], "artista": album['artists'][0]['name'], "capa": album['images'][0]['url']}
    return None

# --- INTERFACE DO USUÁRIO (UI) ---

st.title("🎵 Dueto")
st.write("Descubra novas músicas com seus amigos ou parceiro(a)!")
st.write("Cada pessoa deve inserir 5 de seus álbuns favoritos nos campos abaixo.")

col1, col2 = st.columns(2)
albuns_a = []
albuns_b = []

with col1:
    st.header("Lado A")
    for i in range(5):
        album = st.text_input(f"Álbum A{i+1}", key=f"a{i}")
        albuns_a.append(album)

with col2:
    st.header("Lado B")
    for i in range(5):
        album = st.text_input(f"Álbum B{i+1}", key=f"b{i}")
        albuns_b.append(album)

analisar_btn = st.button("Analisar Dueto")


# --- LÓGICA PRINCIPAL ---

# app.py (substitua todo o bloco if analisar_btn:)

if analisar_btn:
    nomes_albuns_a = [album for album in albuns_a if album]
    nomes_albuns_b = [album for album in albuns_b if album]

    if not nomes_albuns_a or not nomes_albuns_b:
        st.warning("Por favor, preencha pelo menos um álbum para cada lado.")
    else:
        with st.spinner("Analisando gostos e buscando recomendações... 🎶"):
            # Obter a lista de gêneros que a API de recomendação aceita
            generos_validos = obter_generos_validos(sp)

            dados_albuns_a = [buscar_album(nome) for nome in nomes_albuns_a]
            dados_albuns_b = [buscar_album(nome) for nome in nomes_albuns_b]
            
            dados_albuns_a = [a for a in dados_albuns_a if a]
            dados_albuns_b = [a for a in dados_albuns_b if a]

            ids_artistas_semente = []
            generos_semente = set()
            ids_albuns_selecionados = {album['id'] for album in dados_albuns_a + dados_albuns_b}

            for album in dados_albuns_a + dados_albuns_b:
                try:
                    info_album = sp.album(album['id'])
                    id_artista = info_album['artists'][0]['id']
                    if id_artista:
                        ids_artistas_semente.append(id_artista)
                    
                    info_artista = sp.artist(id_artista)
                    if info_artista and info_artista['genres']:
                        # FILTRO CRÍTICO: Adicionamos apenas os gêneros que são válidos como sementes
                        for genero in info_artista['genres']:
                            if genero in generos_validos:
                                generos_semente.add(genero)
                except Exception as e:
                    st.error(f"Ocorreu um erro ao buscar detalhes de um álbum: {e}")

            if not ids_artistas_semente and not generos_semente:
                st.error("Não foi possível encontrar informações suficientes (artistas ou gêneros válidos) para gerar recomendações.")
            else:
                # Se tivermos sementes, continuamos com a lógica
                recomendacoes = sp.recommendations(
                    seed_artists=list(set(ids_artistas_semente))[:3], 
                    seed_genres=list(generos_semente)[:2],
                    limit=20 
                )
                
                # O restante do código para filtrar e exibir as recomendações
                albuns_recomendados = []
                for faixa in recomendacoes['tracks']:
                    album_rec = faixa['album']
                    if album_rec['id'] not in ids_albuns_selecionados:
                        if not any(a['id'] == album_rec['id'] for a in albuns_recomendados):
                             albuns_recomendados.append({
                                "id": album_rec['id'],
                                "nome": album_rec['name'],
                                "artista": album_rec['artists'][0]['name'],
                                "capa": album_rec['images'][0]['url']
                            })
                    if len(albuns_recomendados) >= 5:
                        break

                st.success("Análise Concluída!")
                st.divider()

                st.subheader("Seleções do Dueto")
                sel_col1, sel_col2 = st.columns(2)
                with sel_col1:
                    st.write("**Lado A**")
                    for album in dados_albuns_a:
                        st.image(album['capa'], width=200)
                        st.caption(f"**{album['nome']}** - {album['artista']}")

                with sel_col2:
                    st.write("**Lado B**")
                    for album in dados_albuns_b:
                        st.image(album['capa'], width=200)
                        st.caption(f"**{album['nome']}** - {album['artista']}")
                
                st.divider()
                st.subheader("✨ Recomendações para o Dueto ✨")
                if albuns_recomendados:
                    rec_cols = st.columns(len(albuns_recomendados))
                    for i, album in enumerate(albuns_recomendados):
                        with rec_cols[i]:
                            st.image(album['capa'])
                            st.caption(f"**{album['nome']}**\n\n{album['artista']}")
                else:
                    st.write("Não foi possível gerar recomendações únicas com base nas escolhas.")

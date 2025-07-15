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
except:
    st.error("As credenciais do Spotify não foram encontradas. Verifique seu arquivo .streamlit/secrets.toml")
    st.stop()


# --- FUNÇÕES AUXILIARES ---

def buscar_album(nome_album):
    """Busca um álbum no Spotify e retorna um dicionário com seus dados."""
    if not nome_album:
        return None
    
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=1)
    
    if resultados['albums']['items']:
        album = resultados['albums']['items'][0]
        return {
            "id": album['id'],
            "nome": album['name'],
            "artista": album['artists'][0]['name'],
            "capa": album['images'][0]['url']
        }
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

if analisar_btn:
    nomes_albuns_a = [album for album in albuns_a if album]
    nomes_albuns_b = [album for album in albuns_b if album]

    if not nomes_albuns_a or not nomes_albuns_b:
        st.warning("Por favor, preencha pelo menos um álbum para cada lado.")
    else:
        with st.spinner("Analisando gostos e buscando recomendações... 🎶"):
            dados_albuns_a = [buscar_album(nome) for nome in nomes_albuns_a]
            dados_albuns_b = [buscar_album(nome) for nome in nomes_albuns_b]
            
            dados_albuns_a = [a for a in dados_albuns_a if a]
            dados_albuns_b = [a for a in dados_albuns_b if a]

            ids_artistas_semente = []
            generos_semente = set()
            ids_albuns_selecionados = {album['id'] for album in dados_albuns_a + dados_albuns_b}

            for album in dados_albuns_a + dados_albuns_b:
                info_album = sp.album(album['id'])
                id_artista = info_album['artists'][0]['id']
                if id_artista:
                    ids_artistas_semente.append(id_artista)
                
                info_artista = sp.artist(id_artista)
                if info_artista and info_artista['genres']:
                    generos_semente.update(info_artista['genres'])

            if ids_artistas_semente:
                # API aceita no máximo 5 sementes de cada tipo
                recomendacoes = sp.recommendations(
                    seed_artists=list(set(ids_artistas_semente))[:3], 
                    seed_genres=list(generos_semente)[:2],
                    limit=20 
                )
                
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
            else:
                 st.error("Não foi possível encontrar informações suficientes para gerar recomendações.")
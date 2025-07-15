# app.py (VERSÃO COMPLETA E FINAL)

import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import Counter
import psycopg2 # Biblioteca para conectar ao PostgreSQL

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(layout="wide")

try:
    CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
    DATABASE_URL = st.secrets["DATABASE_URL"] # Carrega a URL do banco de dados
    auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    # Check-up de autenticação
    sp.artist('06HL4z0CvFAxyc27GXpf02') # ID da banda Queen
except Exception as e:
    st.error("🚨 Falha na configuração inicial!")
    st.warning("Verifique se todas as credenciais (Spotify e DATABASE_URL) estão nos seus Secrets (seja no Codespaces ou Streamlit Cloud) e faça o 'Rebuild Container' ou 'Reboot app'.")
    st.stop()

# --- FUNÇÕES DE BANCO DE DADOS ---
@st.cache_resource
def get_db_connection():
    """Estabelece e retorna uma conexão com o banco de dados."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def setup_database(conn):
    """Cria as tabelas do banco de dados se elas não existirem."""
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS Artistas (ID_Artista SERIAL PRIMARY KEY, Nome_Artista VARCHAR(255) NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS Generos (ID_Genero SERIAL PRIMARY KEY, Nome_Genero VARCHAR(100) NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS Albuns (ID_Spotify_Album VARCHAR(255) PRIMARY KEY, Nome_Album VARCHAR(255) NOT NULL, Ano_Lancamento SMALLINT, URL_Capa TEXT, ID_Artista INT NOT NULL, CONSTRAINT fk_artista FOREIGN KEY(ID_Artista) REFERENCES Artistas(ID_Artista) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS Albuns_Generos (ID_Spotify_Album VARCHAR(255) NOT NULL, ID_Genero INT NOT NULL, CONSTRAINT fk_album FOREIGN KEY(ID_Spotify_Album) REFERENCES Albuns(ID_Spotify_Album) ON DELETE CASCADE, CONSTRAINT fk_genero FOREIGN KEY(ID_Genero) REFERENCES Generos(ID_Genero) ON DELETE CASCADE, PRIMARY KEY (ID_Spotify_Album, ID_Genero));
    CREATE TABLE IF NOT EXISTS Duetos (ID_Dueto SERIAL PRIMARY KEY, Data_Criacao TIMESTAMPTZ DEFAULT NOW());
    CREATE TABLE IF NOT EXISTS Selecoes_Albuns (ID_Selecao SERIAL PRIMARY KEY, ID_Dueto INT NOT NULL, ID_Spotify_Album VARCHAR(255) NOT NULL, Tipo_Selecao VARCHAR(20) NOT NULL, Lado CHAR(1), CONSTRAINT fk_dueto FOREIGN KEY(ID_Dueto) REFERENCES Duetos(ID_Dueto) ON DELETE CASCADE, CONSTRAINT fk_album_selecao FOREIGN KEY(ID_Spotify_Album) REFERENCES Albuns(ID_Spotify_Album) ON DELETE CASCADE);
    """
    with conn.cursor() as cur:
        cur.execute(create_tables_sql)
        conn.commit()

def salvar_dados_dueto(conn, albuns_selecionados_a, albuns_selecionados_b, albuns_recomendados):
    """Salva a sessão inteira do dueto no banco de dados."""
    with conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO Duetos DEFAULT VALUES RETURNING ID_Dueto;")
            dueto_id = cur.fetchone()[0]

            def processar_album(album_dict, tipo, lado=None):
                album_info = sp.album(album_dict['id'])
                artista_info = sp.artist(album_info['artists'][0]['id'])
                
                cur.execute("INSERT INTO Artistas (Nome_Artista) VALUES (%s) ON CONFLICT (Nome_Artista) DO NOTHING;", (artista_info['name'],))
                cur.execute("SELECT ID_Artista FROM Artistas WHERE Nome_Artista = %s;", (artista_info['name'],))
                id_artista = cur.fetchone()[0]
                
                cur.execute("INSERT INTO Albuns (ID_Spotify_Album, Nome_Album, Ano_Lancamento, URL_Capa, ID_Artista) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (ID_Spotify_Album) DO NOTHING;", (album_dict['id'], album_dict['nome'], int(album_info['release_date'][:4]), album_dict['capa'], id_artista))

                for genero in artista_info['genres']:
                    cur.execute("INSERT INTO Generos (Nome_Genero) VALUES (%s) ON CONFLICT (Nome_Genero) DO NOTHING;", (genero,))
                    cur.execute("SELECT ID_Genero FROM Generos WHERE Nome_Genero = %s;", (genero,))
                    id_genero = cur.fetchone()[0]
                    cur.execute("INSERT INTO Albuns_Generos (ID_Spotify_Album, ID_Genero) VALUES (%s, %s) ON CONFLICT DO NOTHING;", (album_dict['id'], id_genero))
                
                cur.execute("INSERT INTO Selecoes_Albuns (ID_Dueto, ID_Spotify_Album, Tipo_Selecao, Lado) VALUES (%s, %s, %s, %s);", (dueto_id, album_dict['id'], tipo, lado))

            for album in albuns_selecionados_a: processar_album(album, 'Entrada', 'A')
            for album in albuns_selecionados_b: processar_album(album, 'Entrada', 'B')
            for rec in albuns_recomendados: processar_album(rec['album_data'], 'Recomendacao')

            conn.commit()
            st.toast(f"✅ Dueto #{dueto_id} salvo no banco de dados!")
        except Exception as e:
            conn.rollback()
            st.error(f"Ocorreu um erro ao salvar os dados no banco: {e}")

# --- FUNÇÕES AUXILIARES DA LÓGICA DE RECOMENDAÇÃO ---
def buscar_album(nome_album):
    if not nome_album: return None
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=5)
    return resultados['albums']['items'] if resultados['albums']['items'] else None

def gerar_recomendacoes_alternativas(artistas_ids, generos_artistas):
    recomendacoes = []
    for artista_id in artistas_ids[:3]:
        try:
            artistas_relacionados = sp.artist_related_artists(artista_id)
            for artista_relacionado in artistas_relacionados['artists'][:2]:
                try:
                    albuns = sp.artist_albums(artista_relacionado['id'], album_type='album', limit=2)
                    for album in albuns['items']:
                        if album['images']:
                            recomendacoes.append({'album_data': {'id': album['id'], 'nome': album['name'], 'artista': artista_relacionado['name'], 'capa': album['images'][0]['url']}, 'score': 15, 'popularity': artista_relacionado.get('popularity', 0), 'origem': f"Relacionado a {sp.artist(artista_id)['name']}"})
                except: continue
        except: continue
    generos_principais = [g for g, count in Counter(generos_artistas).most_common(3)]
    for genero in generos_principais:
        try:
            resultados = sp.search(q=f'genre:"{genero}"', type='album', limit=10)
            for album in resultados['albums']['items']:
                if album['images']:
                    recomendacoes.append({'album_data': {'id': album['id'], 'nome': album['name'], 'artista': album['artists'][0]['name'], 'capa': album['images'][0]['url']}, 'score': 10, 'popularity': album.get('popularity', 0), 'origem': f"Gênero: {genero}"})
        except: continue
    return recomendacoes

# --- SESSION STATE E CALLBACKS ---
if 'selecoes' not in st.session_state: st.session_state['selecoes'] = {'a': [None]*5, 'b': [None]*5}
if 'busca' not in st.session_state: st.session_state['busca'] = {}

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
                    st.write(f"**{album_selecionado['nome']}**"); st.caption(album_selecionado['artista'])
                    st.button("Remover", key=f"rem_{slot_key}", on_click=remover_album, args=(lado, i))
            else:
                query = st.text_input("Buscar por nome do álbum", key=f"query_{slot_key}")
                if query: st.session_state.busca[slot_key] = buscar_album(query)
                if slot_key in st.session_state.busca and st.session_state.busca[slot_key]:
                    for res in st.session_state.busca[slot_key]:
                        album_data = {"id": res['id'], "nome": res['name'], "artista": res['artists'][0]['name'], "capa": res['images'][0]['url']}
                        res_col_img, res_col_info, res_col_btn = st.columns([1,2,1])
                        with res_col_img: st.image(album_data['capa'], width=100)
                        with res_col_info: st.write(f"**{album_data['nome']}**"); st.caption(album_data['artista'])
                        with res_col_btn: st.button("Selecionar", key=f"sel_{slot_key}_{album_data['id']}", on_click=selecionar_album, args=(lado, i, album_data))
st.divider()

# --- BOTÃO DE ANÁLISE FINAL E LÓGICA PRINCIPAL ---
analisar_btn = st.button("Analisar Dueto", type="primary", use_container_width=True)

if analisar_btn:
    dados_albuns_a = [album for album in st.session_state.selecoes['a'] if album]
    dados_albuns_b = [album for album in st.session_state.selecoes['b'] if album]
    if not dados_albuns_a or not dados_albuns_b:
        st.warning("É preciso selecionar pelo menos um álbum para cada lado.")
    else:
        with st.spinner("Analisando..."):
            generos_encontrados = []; artistas_ids = set(); albuns_selecionados_ids = {a['id'] for a in dados_albuns_a + dados_albuns_b}
            for album_data in dados_albuns_a + dados_albuns_b:
                try:
                    info_artista = sp.artist(sp.album(album_data['id'])['artists'][0]['id'])
                    artistas_ids.add(info_artista['id']); generos_encontrados.extend(info_artista.get('genres', []))
                except Exception as e: continue
            
            if not artistas_ids:
                st.error("Não foi possível processar os álbuns. Tente novamente."); st.stop()

            recomendacoes = gerar_recomendacoes_alternativas(list(artistas_ids), generos_encontrados)
            recomendacoes_filtradas = [r for r in recomendacoes if r['album_data']['id'] not in albuns_selecionados_ids]
            
            albuns_vistos = set(); recomendacoes_unicas = []
            for rec in recomendacoes_filtradas:
                if rec['album_data']['id'] not in albuns_vistos:
                    albuns_vistos.add(rec['album_data']['id']); recomendacoes_unicas.append(rec)
            
            if not recomendacoes_unicas:
                st.warning("Não foi possível gerar recomendações. Tente com álbuns diferentes.")
            else:
                recomendacoes_ordenadas = sorted(recomendacoes_unicas, key=lambda x: (x['score'], x['popularity']), reverse=True)
                top_recomendacoes = recomendacoes_ordenadas[:5]

                # --- FASE FINAL: PERSISTÊNCIA NO BANCO DE DADOS ---
                try:
                    conn = get_db_connection()
                    setup_database(conn) # Garante que as tabelas existem
                    salvar_dados_dueto(conn, dados_albuns_a, dados_albuns_b, top_recomendacoes)
                except Exception as e:
                    st.error(f"Não foi possível salvar no banco de dados: {e}")

                # --- EXIBIÇÃO DOS RESULTADOS ---
                st.success("✨ Análise Concluída!")
                st.divider()
                st.subheader("🎵 Top 5 Recomendações para o Dueto")
                for i, rec in enumerate(top_recomendacoes):
                    album = rec['album_data']
                    col_img, col_info = st.columns([1, 4])
                    with col_img:
                        if album['capa']: st.image(album['capa'], use_container_width=True)
                    with col_info:
                        st.write(f"**{i+1}. {album['nome']}**"); st.write(f"🎤 Artista: {album['artista']}")
                        st.caption(f"📊 Score: {rec['score']} | 🔥 Popularidade: {rec['popularity']} | 🎯 Origem: {rec['origem']}")
                    st.divider()
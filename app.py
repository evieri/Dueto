# app.py

import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import Counter
import psycopg2

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(layout="wide")

try:
    CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
    DATABASE_URL = st.secrets["DATABASE_URL"] # Carrega a URL do banco
    auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    sp.artist('06HL4z0CvFAxyc27GXpf02') # Check-up
except Exception as e:
    st.error("🚨 Falha na configuração inicial!")
    st.warning("Verifique se todas as credenciais (Spotify e DATABASE_URL) estão nos seus Secrets do Streamlit Cloud.")
    st.stop()

# --- FUNÇÕES DE BANCO DE DADOS ---

# @st.cache_resource gerencia a conexão, mantendo-a viva e evitando múltiplas reconexões.
@st.cache_resource
def get_db_connection():
    """Estabelece e retorna uma conexão com o banco de dados."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def setup_database(conn):
    """Cria as tabelas do banco de dados se elas não existirem."""
    # Este é o código SQL que você gerou anteriormente para criar as tabelas
    # Foi adaptado para o psycopg2 e para não dar erro se a tabela já existir.
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS Artistas (
        ID_Artista SERIAL PRIMARY KEY,
        Nome_Artista VARCHAR(255) NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS Generos (
        ID_Genero SERIAL PRIMARY KEY,
        Nome_Genero VARCHAR(100) NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS Albuns (
        ID_Spotify_Album VARCHAR(255) PRIMARY KEY,
        Nome_Album VARCHAR(255) NOT NULL,
        Ano_Lancamento SMALLINT,
        URL_Capa TEXT,
        ID_Artista INT NOT NULL,
        CONSTRAINT fk_artista FOREIGN KEY(ID_Artista) REFERENCES Artistas(ID_Artista)
    );
    CREATE TABLE IF NOT EXISTS Albuns_Generos (
        ID_Spotify_Album VARCHAR(255) NOT NULL,
        ID_Genero INT NOT NULL,
        CONSTRAINT fk_album FOREIGN KEY(ID_Spotify_Album) REFERENCES Albuns(ID_Spotify_Album),
        CONSTRAINT fk_genero FOREIGN KEY(ID_Genero) REFERENCES Generos(ID_Genero),
        PRIMARY KEY (ID_Spotify_Album, ID_Genero)
    );
    CREATE TABLE IF NOT EXISTS Duetos (
        ID_Dueto SERIAL PRIMARY KEY,
        Data_Criacao TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS Selecoes_Albuns (
        ID_Selecao SERIAL PRIMARY KEY,
        ID_Dueto INT NOT NULL,
        ID_Spotify_Album VARCHAR(255) NOT NULL,
        Tipo_Selecao VARCHAR(20) NOT NULL, -- 'Entrada' ou 'Recomendacao'
        Lado CHAR(1), -- 'A', 'B' ou NULL
        CONSTRAINT fk_dueto FOREIGN KEY(ID_Dueto) REFERENCES Duetos(ID_Dueto),
        CONSTRAINT fk_album_selecao FOREIGN KEY(ID_Spotify_Album) REFERENCES Albuns(ID_Spotify_Album)
    );
    """
    with conn.cursor() as cur:
        cur.execute(create_tables_sql)
        conn.commit()

def salvar_dados_dueto(conn, albuns_selecionados, albuns_recomendados):
    """Salva a sessão inteira do dueto no banco de dados."""
    with conn.cursor() as cur:
        try:
            # Fase 1: Salvar o evento principal do Dueto e obter seu ID
            cur.execute("INSERT INTO Duetos DEFAULT VALUES RETURNING ID_Dueto;")
            dueto_id = cur.fetchone()[0]

            # Função auxiliar para salvar um único álbum e suas associações
            def processar_album(album_dict, tipo, lado=None):
                # Salva o Artista (ignora se já existe)
                cur.execute("INSERT INTO Artistas (Nome_Artista) VALUES (%s) ON CONFLICT (Nome_Artista) DO NOTHING;", (album_dict['artista'],))
                cur.execute("SELECT ID_Artista FROM Artistas WHERE Nome_Artista = %s;", (album_dict['artista'],))
                id_artista = cur.fetchone()[0]

                # Salva o Álbum (ignora se já existe)
                album_info = sp.album(album_dict['id'])
                cur.execute(
                    """
                    INSERT INTO Albuns (ID_Spotify_Album, Nome_Album, Ano_Lancamento, URL_Capa, ID_Artista)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT (ID_Spotify_Album) DO NOTHING;
                    """,
                    (album_dict['id'], album_dict['nome'], int(album_info['release_date'][:4]), album_dict['capa'], id_artista)
                )

                # Salva os Gêneros e a relação Álbum-Gênero
                generos_artista = sp.artist(album_info['artists'][0]['id'])['genres']
                for genero in generos_artista:
                    cur.execute("INSERT INTO Generos (Nome_Genero) VALUES (%s) ON CONFLICT (Nome_Genero) DO NOTHING;", (genero,))
                    cur.execute("SELECT ID_Genero FROM Generos WHERE Nome_Genero = %s;", (genero,))
                    id_genero = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO Albuns_Generos (ID_Spotify_Album, ID_Genero) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                        (album_dict['id'], id_genero)
                    )
                
                # Finalmente, salva a seleção
                cur.execute(
                    "INSERT INTO Selecoes_Albuns (ID_Dueto, ID_Spotify_Album, Tipo_Selecao, Lado) VALUES (%s, %s, %s, %s);",
                    (dueto_id, album_dict['id'], tipo, lado)
                )

            # Processa todos os álbuns selecionados
            for album in albuns_selecionados['a']:
                processar_album(album, 'Entrada', 'A')
            for album in albuns_selecionados['b']:
                processar_album(album, 'Entrada', 'B')

            # Processa todos os álbuns recomendados
            for rec in albuns_recomendados:
                processar_album(rec['album_data'], 'Recomendacao')

            conn.commit()
            st.toast(f"✅ Dueto #{dueto_id} salvo no banco de dados!")

        except Exception as e:
            conn.rollback() # Desfaz as alterações se ocorrer um erro
            st.error(f"Ocorreu um erro ao salvar os dados: {e}")

# --- FUNÇÕES AUXILIARES ---
def buscar_album(nome_album):
    """Busca um álbum no Spotify e retorna um dicionário com seus dados."""
    if not nome_album: return None
    resultados = sp.search(q=f"album:{nome_album}", type="album", limit=5)
    if resultados['albums']['items']:
        return resultados['albums']['items']
    return None

def gerar_recomendacoes_alternativas(artistas_ids, generos_artistas):
    """Gera recomendações usando busca por artistas similares e álbuns populares."""
    recomendacoes = []
    
    # Método 1: Buscar álbuns de artistas relacionados
    for artista_id in artistas_ids[:3]:  # Limita a 3 artistas para não sobrecarregar
        try:
            # Busca artistas relacionados
            artistas_relacionados = sp.artist_related_artists(artista_id)
            
            for artista_relacionado in artistas_relacionados['artists'][:5]:  # Top 5 relacionados
                try:
                    # Busca álbuns do artista relacionado
                    albuns = sp.artist_albums(artista_relacionado['id'], album_type='album', limit=3)
                    
                    for album in albuns['items']:
                        if album['images']:  # Só adiciona se tiver imagem
                            recomendacoes.append({
                                'album_data': {
                                    'id': album['id'],
                                    'nome': album['name'],
                                    'artista': artista_relacionado['name'],
                                    'capa': album['images'][0]['url']
                                },
                                'score': 15,  # Score alto para artistas relacionados
                                'popularity': artista_relacionado.get('popularity', 0),
                                'origem': f"Relacionado a {sp.artist(artista_id)['name']}"
                            })
                except:
                    continue
        except:
            continue
    
    # Método 2: Buscar por gêneros usando search
    generos_principais = [g for g, count in Counter(generos_artistas).most_common(3)]
    
    for genero in generos_principais:
        try:
            # Busca álbuns por gênero
            resultados = sp.search(q=f'genre:"{genero}"', type='album', limit=20)
            
            for album in resultados['albums']['items']:
                if album['images']:
                    recomendacoes.append({
                        'album_data': {
                            'id': album['id'],
                            'nome': album['name'],
                            'artista': album['artists'][0]['name'],
                            'capa': album['images'][0]['url']
                        },
                        'score': 10,  # Score médio para busca por gênero
                        'popularity': album.get('popularity', 0),
                        'origem': f"Gênero: {genero}"
                    })
        except:
            continue
    
    # Método 3: Buscar álbuns populares dos próprios artistas
    for artista_id in artistas_ids:
        try:
            albuns = sp.artist_albums(artista_id, album_type='album', limit=5)
            artista_nome = sp.artist(artista_id)['name']
            
            for album in albuns['items']:
                if album['images']:
                    recomendacoes.append({
                        'album_data': {
                            'id': album['id'],
                            'nome': album['name'],
                            'artista': artista_nome,
                            'capa': album['images'][0]['url']
                        },
                        'score': 8,  # Score menor para mesmo artista
                        'popularity': album.get('popularity', 0),
                        'origem': f"Mais de {artista_nome}"
                    })
        except:
            continue
    
    return recomendacoes

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
            # (Esta parte permanece a mesma)
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

            # --- FASE 2: GERAÇÃO DE CANDIDATOS COM PLANO A E PLANO B ---
            # (Esta parte permanece a mesma)
            recomendacoes_api = None
            params_a = {'limit': 25}
            sementes_artistas = list(artistas_fonte_ids)[:3]
            top_generos = [g for g, c in Counter(gostos_de_genero).most_common(2)]
            if sementes_artistas: params_a['seed_artists'] = sementes_artistas
            if top_generos: params_a['seed_genres'] = top_generos
            
            try:
                if 'seed_artists' in params_a or 'seed_genres' in params_a:
                    recomendacoes_api = sp.recommendations(**params_a)
            except Exception:
                recomendacoes_api = None

            if not recomendacoes_api or not recomendacoes_api.get('tracks'):
                try:
                    params_b = {'limit': 25, 'seed_tracks': list(albuns_selecionados_ids)[:5]}
                    recomendacoes_api = sp.recommendations(**params_b)
                except Exception as e:
                    st.error("Ocorreu um erro ao buscar recomendações do Spotify. Tente uma combinação diferente de álbuns.")
                    st.stop()

            # --- FASE 3: SISTEMA DE PONTUAÇÃO (COM CORREÇÃO NA POPULARIDADE) ---
            if not recomendacoes_api or not recomendacoes_api.get('tracks'):
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
                st.stop()

            candidatos_pontuados = []
            artistas_processados = {}
            for faixa in recomendacoes_api['tracks']:
                album_candidato = faixa['album']
                if album_candidato['id'] in albuns_selecionados_ids or any(c['album_data']['id'] == album_candidato['id'] for c in candidatos_pontuados):
                    continue

                # ---- MUDANÇA CRÍTICA AQUI ----
                # Busca os detalhes COMPLETOS do álbum para pegar a popularidade correta
                try:
                    album_completo = sp.album(album_candidato['id'])
                    popularidade_album = album_completo.get('popularity', 0)
                except:
                    popularidade_album = 0 # Se a busca falhar, assume 0
                
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
                    "popularity": popularidade_album # Usa o valor correto
                })

            # --- FASE 4: CLASSIFICAÇÃO FINAL (COM EXIBIÇÃO DA POPULARIDADE) ---
            if not candidatos_pontuados:
                st.warning("Não foi possível gerar recomendações com base na combinação de gostos. Tente outros álbuns!")
            else:
                candidatos_ordenados = sorted(candidatos_pontuados, key=lambda x: (x['score'], x['popularity']), reverse=True)
                top_5_recomendacoes = candidatos_ordenados[:5]
                st.success("Análise Concluída!")
                st.divider()
                st.subheader("✨ Top 5 Recomendações para o Dueto ✨")
                
                for i, rec in enumerate(top_5_recomendacoes):
                    album = rec['album_data']
                    col_img, col_info = st.columns([1, 4])
                    with col_img:
                        st.image(album['capa'], use_container_width=True)
                    with col_info:
                        st.write(f"**{i+1}. {album['nome']}**")
                        st.write(f"Artista: {album['artista']}")
                        # Adicionamos a popularidade na exibição
                        st.caption(f"Pontuação de Sintonia: {rec['score']} | 🔥 Popularidade: {rec['popularity']}")
                    st.divider()

    # --- FASE 5: PERSISTÊNCIA NO BANCO DE DADOS ---
    if 'top_5_recomendacoes' in locals() and top_5_recomendacoes:
        try:
            conn = get_db_connection()
            setup_database(conn) # Garante que as tabelas existem
            
            albuns_selecionados_para_db = {
                'a': [album for album in st.session_state.selecoes['a'] if album],
                'b': [album for album in st.session_state.selecoes['b'] if album]
            }
            salvar_dados_dueto(conn, albuns_selecionados_para_db, top_5_recomendacoes)
        except Exception as e:
            st.error("Não foi possível conectar ou salvar no banco de dados.")
            st.error(e)
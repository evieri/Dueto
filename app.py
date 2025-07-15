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
                            # Busca informações completas do álbum para obter popularidade
                            try:
                                album_completo = sp.album(album['id'])
                                popularidade = album_completo.get('popularity', 0)
                            except:
                                popularidade = artista_relacionado.get('popularity', 0)
                            
                            recomendacoes.append({
                                'album_data': {
                                    'id': album['id'],
                                    'nome': album['name'],
                                    'artista': artista_relacionado['name'],
                                    'capa': album['images'][0]['url']
                                },
                                'score': 15,  # Score alto para artistas relacionados
                                'popularity': popularidade,
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
                    # Para álbuns de search, tenta buscar popularidade completa
                    try:
                        album_completo = sp.album(album['id'])
                        popularidade = album_completo.get('popularity', 0)
                    except:
                        # Se não conseguir, usa popularidade do artista
                        try:
                            artista_info = sp.artist(album['artists'][0]['id'])
                            popularidade = artista_info.get('popularity', 0)
                        except:
                            popularidade = 0
                    
                    recomendacoes.append({
                        'album_data': {
                            'id': album['id'],
                            'nome': album['name'],
                            'artista': album['artists'][0]['name'],
                            'capa': album['images'][0]['url']
                        },
                        'score': 10,  # Score médio para busca por gênero
                        'popularity': popularidade,
                        'origem': f"Gênero: {genero}"
                    })
        except:
            continue
    
    # Método 3: Buscar álbuns populares dos próprios artistas
    for artista_id in artistas_ids:
        try:
            albuns = sp.artist_albums(artista_id, album_type='album', limit=5)
            artista_info = sp.artist(artista_id)
            artista_nome = artista_info['name']
            artista_popularidade = artista_info.get('popularity', 0)
            
            for album in albuns['items']:
                if album['images']:
                    # Tenta buscar popularidade específica do álbum
                    try:
                        album_completo = sp.album(album['id'])
                        popularidade = album_completo.get('popularity', artista_popularidade)
                    except:
                        popularidade = artista_popularidade
                    
                    recomendacoes.append({
                        'album_data': {
                            'id': album['id'],
                            'nome': album['name'],
                            'artista': artista_nome,
                            'capa': album['images'][0]['url']
                        },
                        'score': 8,  # Score menor para mesmo artista
                        'popularity': popularidade,
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
        with st.spinner("Analisando seus gostos e buscando recomendações... 🎶"):
            try:
                # --- FASE 1: COLETA DE DADOS ---
                generos_encontrados = []
                artistas_ids = set()
                albuns_selecionados_ids = {album['id'] for album in dados_albuns_a + dados_albuns_b}

                for album_data in dados_albuns_a + dados_albuns_b:
                    try:
                        album_info = sp.album(album_data['id'])
                        artista_id = album_info['artists'][0]['id']
                        info_artista = sp.artist(artista_id)
                        
                        artistas_ids.add(artista_id)
                        generos_encontrados.extend(info_artista.get('genres', []))
                        
                    except Exception as e:
                        st.warning(f"Erro ao processar álbum {album_data['nome']}: {e}")
                        continue

                if not artistas_ids:
                    st.error("Não foi possível processar nenhum álbum. Tente novamente.")
                    st.stop()

                # --- FASE 2: GERAÇÃO DE RECOMENDAÇÕES ALTERNATIVAS ---
                st.info("🔄 Gerando recomendações usando artistas relacionados e busca por gêneros...")
                
                recomendacoes = gerar_recomendacoes_alternativas(list(artistas_ids), generos_encontrados)
                
                # Remove álbuns já selecionados
                recomendacoes_filtradas = [
                    rec for rec in recomendacoes 
                    if rec['album_data']['id'] not in albuns_selecionados_ids
                ]
                
                # Remove duplicatas
                albuns_vistos = set()
                recomendacoes_unicas = []
                for rec in recomendacoes_filtradas:
                    if rec['album_data']['id'] not in albuns_vistos:
                        albuns_vistos.add(rec['album_data']['id'])
                        recomendacoes_unicas.append(rec)

                if not recomendacoes_unicas:
                    st.warning("Não foi possível gerar recomendações. Tente com álbuns diferentes.")
                else:
                    # Ordena por score e popularidade
                    recomendacoes_ordenadas = sorted(
                        recomendacoes_unicas, 
                        key=lambda x: (x['score'], x['popularity']), 
                        reverse=True
                    )
                    
                    # Pega top 5 recomendações
                    top_recomendacoes = recomendacoes_ordenadas[:5]
                    
                    st.success("✨ Análise Concluída!")
                    st.divider()
                    st.subheader("🎵 Top 5 Recomendações para o Dueto")
                    st.write("Baseado em artistas relacionados e análise de gêneros!")
                    
                    for i, rec in enumerate(top_recomendacoes):
                        album = rec['album_data']
                        col_img, col_info = st.columns([1, 4])
                        with col_img:
                            if album['capa']:
                                st.image(album['capa'], use_container_width=True)
                        with col_info:
                            st.write(f"**{i+1}. {album['nome']}**")
                            st.write(f"🎤 Artista: {album['artista']}")
                            st.caption(f"📊 Score: {rec['score']} | 🎯 {rec['origem']}")
                        st.divider()

                    # Mostra estatísticas
                    st.subheader("📊 Análise do Dueto")
                    col_stats1, col_stats2 = st.columns(2)
                    
                    with col_stats1:
                        st.metric("Artistas Analisados", len(artistas_ids))
                        st.metric("Álbuns Selecionados", len(dados_albuns_a + dados_albuns_b))
                    
                    with col_stats2:
                        st.metric("Gêneros Encontrados", len(set(generos_encontrados)))
                        st.metric("Recomendações Geradas", len(recomendacoes_unicas))
                    
                    if generos_encontrados:
                        st.write("🎨 **Gêneros do seu dueto:**")
                        generos_contados = Counter(generos_encontrados)
                        for genero, count in generos_contados.most_common(5):
                            st.write(f"• {genero.title()} ({count}x)")

            except Exception as e:
                st.error(f"Erro inesperado durante a análise: {e}")
                st.write("Tente novamente com álbuns diferentes.")

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
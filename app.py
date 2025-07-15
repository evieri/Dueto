# app.py (VERSÃO FINAL CORRIGIDA E INTEGRADA)

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
    DATABASE_URL = st.secrets["DATABASE_URL"]
    auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    sp.artist('06HL4z0CvFAxyc27GXpf02') # Check-up de autenticação
except Exception as e:
    st.error("🚨 Falha na configuração inicial!")
    st.warning("Verifique se TODAS as 3 credenciais (Spotify ID, Secret e DATABASE_URL) estão corretas nos seus Secrets e faça o 'Rebuild Container'/'Reboot app'.")
    st.stop()

# --- FUNÇÕES DE BANCO DE DADOS ---
@st.cache_resource
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def setup_database(conn):
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
    with conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO Duetos DEFAULT VALUES RETURNING ID_Dueto;")
            dueto_id = cur.fetchone()[0]

            def processar_album(album_dict
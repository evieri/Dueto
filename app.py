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
                    st.image(album_selecionado['capa'], use_column_width=True)
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
        # A lógica de recomendação que você já tem, agora usando dados 100% confiáveis
        with st.spinner("Analisando..."):
            ids_artistas_semente = []
            generos_semente = set()
            ids_albuns_selecionados = {album['id'] for album in dados_albuns_a + dados_albuns_b}
            
            # (O resto da sua lógica de recomendação pode ser colado aqui)
            # Exemplo simplificado:
            st.success("Análise Concluída! Lógica de recomendação a ser implementada.")
            st.write("**Álbuns Lado A:**")
            st.json([a['nome'] for a in dados_albuns_a])
            st.write("**Álbuns Lado B:**")
            st.json([b['nome'] for b in dados_albuns_b])
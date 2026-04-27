import streamlit as st
import os
import tempfile

from rag_engine import ManualRAG

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="RAG Asistent Oracle", page_icon="🤖", layout="wide")

# 1. Inițializăm un uploader_key în session_state dacă nu există
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# --- INITIALIZARE SISTEM (Cache) ---
@st.cache_resource(show_spinner="Se conectează la baza de date și se încarcă modelele AI. Te rog așteaptă...")
def init_rag_system():
    rag = ManualRAG()
    rag.load_from_db(device="cpu")
    return rag


rag_app = init_rag_system()


# --- FUNCȚII AJUTĂTOARE PENTRU DB ---
def get_uploaded_documents():
    """Interoghează baza de date Oracle pentru a vedea documentele unice."""
    try:
        # Ne folosim de conexiunea existentă din rag_app.store
        with rag_app.store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT DISTINCT doc_name FROM {rag_app.store.table_name}")
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        return []


# --- NAVIGARE (SIDEBAR) ---
st.sidebar.title("Meniu Navigare")
page = st.sidebar.radio("Mergi la:", [
    "💬 Chat cu Documentele",
    "🔍 Căutare Semantică",
    "📁 Gestionare Documente"
])

st.sidebar.markdown("---")
st.sidebar.info("Sistem RAG susținut de Oracle AI Vector Search și modele locale.")

# ==========================================
# PAGINA 1: CHAT PRINCIPAL
# ==========================================
if page == "💬 Chat cu Documentele":
    st.title("Asistent Inteligent (RAG)")
    st.write("Pune o întrebare bazată pe documentele deja încărcate în baza de date Oracle.")

    # Inițializăm istoricul conversației în memorie (session_state)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Afișăm istoricul mesajelor
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Căsuța de input pentru utilizator
    if prompt := st.chat_input("Scrie întrebarea ta aici..."):
        # Afișăm mesajul utilizatorului
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Generăm răspunsul
        with st.chat_message("ai"):
            with st.spinner("Caut informații și generez răspunsul..."):
                # Convertim istoricul din Streamlit în formatul acceptat de codul tău
                history_for_rag = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]

                response = rag_app.ask(prompt, conversation_history=history_for_rag)

                st.markdown(response)

        # Salvăm răspunsul în istoric
        st.session_state.messages.append({"role": "ai", "content": response})
# ==========================================
# PAGINA 2: CĂUTARE SEMANTICĂ
# ==========================================
elif page == "🔍 Căutare Semantică":
    st.title("🔍 Căutare Semantică Articole")
    st.write(
        "Introdu o temă, un subiect sau o întrebare. Sistemul va căuta prin vectori și va returna cele mai relevante fragmente și abstracte din articolele tale.")

    # Căsuța de căutare
    search_query = st.text_input("Ce subiect cauți? (ex: 'analiză statică a codului', 'vulnerabilități python')",
                                 key="semantic_search_input")

    if st.button("Caută Documente", type="primary"):
        if search_query:
            with st.spinner("Scanez vectorii în baza de date Oracle..."):
                # Apelăm funcția nouă creată în rag_engine.py
                results = rag_app.semantic_search(search_query, top_k=5)

                if results:
                    st.success(f"Am găsit {len(results)} secțiuni relevante:")

                    # Afișăm rezultatele frumos, în containere expandabile
                    for i, res in enumerate(results):
                        # Convertim scorul într-un procent pentru a fi mai ușor de citit
                        match_percentage = res['score'] * 100

                        with st.expander(
                                f"📄 {res['doc_name']} (Pagina {res['page']}) - Relevanță: {match_percentage:.1f}%",
                                expanded=(i == 0)):
                            # Marcăm textul care acționează ca abstract/extras
                            st.markdown("**Extras din document:**")
                            st.info(res['text'])
                else:
                    st.warning("Nu am găsit niciun articol care să se potrivească cu căutarea ta.")
        else:
            st.warning("Te rog să introduci un termen de căutare.")
# ==========================================
# PAGINA 3: GESTIONARE DOCUMENTE
# ==========================================
elif page == "📁 Gestionare Documente":
    st.title("Baza de Date Articole")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Documente Prezente")
        docs = get_uploaded_documents()
        if docs:
            for doc in docs:
                st.info(f"📄 **{doc}**")
        else:
            st.info("Nu există documente în baza de date.")

    with col2:
        st.subheader("Încarcă Articol Nou")

        with st.container():
            doc_title = st.text_input("Titlu Articol (ex: Raport BNR 2024):",
                                      key=f"title_{st.session_state.uploader_key}")
            uploaded_file = st.file_uploader("Alege un fișier PDF", type=["pdf"],
                                             key=f"up_{st.session_state.uploader_key}")

            if st.button("Procesează și Inserează în Oracle"):
                if uploaded_file is not None:
                    with st.spinner("Se procesează..."):
                        # Determinăm ce nume să folosim în DB
                        # Dacă utilizatorul nu pune titlu, folosim numele original al fișierului
                        final_name = doc_title.strip() if doc_title.strip() else uploaded_file.name

                        # Creăm un fișier temporar
                        temp_dir = tempfile.gettempdir()
                        tmp_file_path = os.path.join(temp_dir, uploaded_file.name)

                        with open(tmp_file_path, "wb") as f:
                            f.write(uploaded_file.getvalue())

                        try:
                            # Apelăm setup-ul modificat cu final_name
                            rag_app.setup([tmp_file_path], display_name=final_name)

                            st.success(f"✅ Documentul '{final_name}' a fost indexat!")

                            # 2. INCREMENTĂM CHEIA pentru a curăța input-urile la următorul rerun
                            st.session_state.uploader_key += 1

                            # Așteptăm puțin să vadă mesajul, apoi dăm rerun
                            import time

                            time.sleep(2)
                            st.rerun()

                        except Exception as e:
                            st.error(f"Eroare: {e}")
                        finally:
                            if os.path.exists(tmp_file_path):
                                os.unlink(tmp_file_path)
                else:
                    st.warning("Încarcă un PDF.")
import os
import streamlit as st
import threading
import json
import asyncio
import edge_tts
from crewai import Agent, Crew, Process, Task
from crewai_tools import SerperDevTool
from fpdf import FPDF
from github import Github
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Dict

# --- CONFIGURAZIONE DELLA PAGINA WEB ---
st.set_page_config(page_title="Universal AI Agency V2", page_icon="🤖", layout="wide")

# --- GESTIONE SICUREZZA / PASSWORD ---
PASSWORD_CORRETTA = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "IlTuoDelfinoSegreto2026"))

if "autenticato" not in st.session_state:
    st.session_state.autenticato = False

def verifica_password():
    if st.session_state["password_inserita"] == PASSWORD_CORRETTA:
        st.session_state.autenticato = True
        del st.session_state["password_inserita"]
    else:
        st.session_state.autenticato = False
        st.error("❌ Password errata. Riprova.")

if not st.session_state.autenticato:
    st.title("🔒 Accesso Riservato - AI Agency V2")
    st.text_input(
        "Inserisci la password di sblocco:", 
        type="password", 
        key="password_inserita",
        on_change=verifica_password
    )
    st.stop()

# ----------------------------------------------------------------------
# SCHEMI SCHELETRO PYDANTIC PER IL PARSING RIGIDO DEI CONTENUTI
# ----------------------------------------------------------------------

class ValidazioneAgente(BaseModel):
    agente: str = Field(description="Nome dell'agente esperto che esegue la valutazione.")
    esito: str = Field(description="Tassativamente espresso come APPROVATO o DISAPPROVATO.")
    motivazione: str = Field(description="Spiegazione tecnica, logistica o culturale approfondita della scelta.")
    controproposta: str = Field(description="La contromossa esatta o la variante che l'agente approverebbe al 100%.")

class StatoTavolaRotonda(BaseModel):
    piano_finale_concordato: str = Field(description="Il testo completo, dettagliato ed esteso dell'itinerario o piano d'azione finale senza tagli.")
    verbale_validazioni: List[ValidazioneAgente] = Field(description="L'elenco strutturato dei pareri e delle schede di ogni singolo agente.")
    nota_psicologica_riassuntiva: str = Field(description="Riflessione finale su come le relazioni di fiducia e le analisi psicologiche hanno influenzato il voto d'aula.")

# ----------------------------------------------------------------------
# UTILITIES: PDF, AUDIO MULTI-VOCE, PERSONAGGI E INTERFACCIA GITHUB
# ----------------------------------------------------------------------

def esporta_in_pdf(testo_output, testo_discussione, nome_config):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Output Finale Strutturato - Sessione: {nome_config}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", size=11)
    
    testo_pulito_out = testo_output.replace("•", "-").replace("’", "'").replace("“", '"').replace("”", '"').encode("latin-1", "ignore").decode("latin-1")
    pdf.multi_cell(0, 6, testo_pulito_out)
    
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "💬 Verbale della Sessione e Trascrizioni", ln=True)
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 10)
    
    testo_pulito_disc = testo_discussione.replace("•", "-").replace("’", "'").replace("“", '"').replace("”", '"').encode("latin-1", "ignore").decode("latin-1")
    pdf.multi_cell(0, 5, testo_pulito_disc)
    
    return pdf.output(dest='S')

def genera_audio_multivoce(testo_discussione, agenti_data):
    voci_disponibili = ["it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-BenignoNeural", "it-IT-IsabellaNeural"]
    mappa_voci = {}
    
    for i in range(min(4, len(agenti_data))):
        nome_agente = agenti_data[i]['name']
        mappa_voci[nome_agente.strip().lower()] = voci_disponibili[i]

    righe = testo_discussione.split("\n")
    
    async def amain():
        combined_audio = b""
        voce_attuale = "it-IT-DiegoNeural"
        
        for riga in righe:
            riga_strip = riga.strip()
            if not riga_strip:
                continue
                
            tag_rilevato = False
            for nome_agente, voce in mappa_voci.items():
                if riga.lower().startswith(f"{nome_agente}:") or \
                   riga.lower().startswith(f"agente {nome_agente}:") or \
                   f"agente: {nome_agente}" in riga.lower():
                    voce_attuale = voce
                    tag_rilevato = True
                    break
            
            if not tag_rilevato and (riga_strip.startswith("===") or riga_strip.startswith("👤")):
                 voce_attuale = "it-IT-DiegoNeural"

            testo_riga = riga_strip.replace("•", "").replace("*", "").replace("├", "").replace("└", "").replace("  ", " ").strip()
            if not testo_riga:
                continue
                
            try:
                communicate = edge_tts.Communicate(testo_riga, voce_attuale)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        combined_audio += chunk["data"]
            except Exception as e:
                print(f"Errore TTS sulla riga: {testo_riga}. Errore: {e}")
                pass
        return combined_audio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    audio_bytes = loop.run_until_complete(amain())
    return audio_bytes

def salva_file_su_github(token, repo_name, file_content, path_file, commit_msg):
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents(path_file, ref="main")
            repo.update_file(contents.path, commit_msg, file_content, contents.sha, branch="main")
        except:
            repo.create_file(path_file, commit_msg, file_content, branch="main")
        return True
    except Exception as e:
        st.error(f"Errore critico GitHub nel percorso ({path_file}): {e}")
        return False

def carica_configurazioni_da_github(token, repo_name):
    configs = {}
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents("config", ref="main")
            for file_content in contents:
                if file_content.name.endswith(".json"):
                    nome_config = file_content.name.replace(".json", "")
                    raw_data = file_content.decoded_content.decode("utf-8")
                    configs[nome_config] = json.loads(raw_data)
        except Exception as e:
            print(f"Nessuna cartella 'config' trovata o errore di lettura: {e}")
            pass
    except Exception as e:
        print(f"Errore connessione GitHub per caricamento config: {e}")
        pass
    return configs

def carica_personaggi_da_github(token, repo_name):
    personaggi = {}
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents("characters", ref="main")
            for file_content in contents:
                if file_content.name.endswith(".json"):
                    nome_char = file_content.name.replace(".json", "").replace("_", " ").title()
                    raw_data = file_content.decoded_content.decode("utf-8")
                    personaggi[nome_char] = json.loads(raw_data)
        except:
            pass
    except:
        pass
    return personaggi

# ----------------------------------------------------------------------
# FUNZIONE CORE DI RAGIONAMENTO IN BACKGROUND (CON SEARCH FILTRATO)
# ----------------------------------------------------------------------

def esegui_agenti_background(gemini_key, serper_key, gh_token, gh_repo, nome_config, agenti_data, matrice_data, profili_data, istruzioni_task, max_giri):
    try:
        os.environ["GEMINI_API_KEY"] = gemini_key
        if serper_key:
            os.environ["SERPER_API_KEY"] = serper_key
        
        contesto_psicologico = "\n--- CONTESTO RELAZIONALE E PSICOLOGICO DEL TEAM ---\n"
        contesto_psicologico += "Determinazione/Peso (Weight) attuale degli agenti:\n"
        for d in agenti_data:
            abilita_ricerca = "📶 Connesso a Internet" if d.get('has_search', False) else "📴 Offline (Solo Logica Interna)"
            contesto_psicologico += f"- Agente {d['name']}: Peso {d['weight']}/1.0 | {abilita_ricerca}\n"
        
        contesto_psicologico += "\nMatrice di Fiducia Incrociata (Peer Review):\n"
        contesto_psicologico += matrice_data.to_string() + "\n"
        
        contesto_psicologico += "\nProfili Psicologici Dinamici (Analisi Interne):\n"
        for d in profili_data:
            contesto_psicologico += f"--- Analisi di {d['analista']} ---\n"
            for target, analisi in d['analisi'].items():
                contesto_psicologico += f"  > Verso {target}: {analisi}\n"
        contesto_psicologico += "--------------------------------------------------\n\n"

        crew_agents = []
        for i in range(min(4, len(agenti_data))):
            d = agenti_data[i]
            
            mio_profilo_coffe = ""
            for p in profili_data:
                if p['analista'].lower() == d['name'].lower():
                    mio_profilo_coffe = "\nLe tue analisi psicologiche interne sui colleghi:\n"
                    for target, analisi in p['analisi'].items():
                        mio_profilo_coffe += f"- Verso {target}: {analisi}\n"
                    break

            full_backstory = f"Il tuo nome proprio è {d['name']}. {d['backstory']}. " \
                             f"La tua determinazione decisionale (peso di voto) è {d['weight']}. " \
                             f"{mio_profilo_coffe}"

            mia_fiducia_verso_altri = matrice_data.loc[d['name']].to_dict()
            fiducia_str = ", ".join([f"{k}: {v}" for k, v in mia_fiducia_verso_altri.items() if k != d['name']])
            full_goal = f"Ti chiami {d['name']}. Il tuo obiettivo è: {d['goal']}. " \
                        f"I tuoi livelli di fiducia attuali verso i colleghi sono: {fiducia_str}. " \
                        f"Modula le tue approvazioni/rifiuti in base a questa fiducia."

            tools_agente = []
            if d.get('has_search', False) and serper_key:
                try:
                    tools_agente.append(SerperDevTool())
                except Exception as e:
                    print(f"Errore caricamento Serper tool per {d['name']}: {e}")

            a = Agent(
                role=d['role'],
                goal=full_goal,
                backstory=full_backstory,
                llm="gemini/gemini-1.5-pro",
                verbose=True,
                allow_delegation=True,
                tools=tools_agente
            )
            crew_agents.append(a)
            
        manager_agent = crew_agents[3] 

        task_description = f"{contesto_psicologico}" \
                           f"Obiettivo Universale da risolvere alla tavola rotonda: {istruzioni_task}. " \
                           f"Istruzioni di Protocollo Rigide per il Manager e gli Esperti:\n" \
                           f"1. Raccogliete i pareri di tutti. Gli agenti con il tool di ricerca lo usino se incontrano dati sconosciuti.\n" \
                           f"2. Se sorge un conflitto, l'agente con la fiducia o il peso più alto vince la trattativa.\n" \
                           f"3. Il Manager ha l'obbligo di mappare accuratamente i contenuti nel modello Pydantic richiesto.\n" \
                           f"4. Mantieni l'intero itinerario/piano esteso all'interno del campo 'piano_finale_concordato' senza tagliare i dettagli costruttivi."

        task = Task(
            description=task_description,
            expected_output="Un oggetto JSON validato da Pydantic contenente il piano finale, la lista dei box di validazione di ciascun agente e la nota relazionale complessiva.",
            agent=manager_agent,
            max_iter=max_giri,
            output_pydantic=StatoTavolaRotonda
        )

        crew = Crew(
            agents=crew_agents, 
            tasks=[task], 
            process=Process.hierarchical, 
            manager_agent=manager_agent, 
            verbose=True,
            memory=True
        )
        
        print(f"⚡ Avvio Crew strutturata per '{nome_config}'...")
        crew_output = crew.kickoff()
        
        pydantic_res = crew_output.pydantic
        
        risultato_finale = f"=== PIANO FINALE CONCORDATO ===\n{pydantic_res.piano_finale_concordato}\n\n"
        risultato_finale += "=== VERBALE DELLE VALIDAZIONI DEI SINGOLI AGENTI ===\n"
        for v in pydantic_res.verbale_validazioni:
            risultato_finale += f"\n👤 Agente Esperto: {v.agente}\n"
            risultato_finale += f"  ├ Esito formale: {v.esito}\n"
            risultato_finale += f"  ├ Motivazione Espressa: {v.motivazione}\n"
            risultato_finale += f"  └ Soluzione/Controproposta: {v.controproposta}\n"
        risultato_finale += f"\n=== NOTA DI DEBRIEFING PSICOLOGICO ===\n{pydantic_res.nota_psicologica_riassuntiva}"
        
        stringa_discussione = f"Trascrizione Ufficiale dei Box Decisionali - Sessione: {nome_config}\n"
        stringa_discussione += "==================================================================\n\n"
        stringa_discussione += resultado_finale
        
        nome_base = nome_config.lower().replace(' ', '_')

        print(f"📄 Esportazione PDF strutturato per '{nome_config}'...")
        pdf_bytes = esporta_in_pdf(risultato_finale, stringa_discussione, nome_config)
        salva_file_su_github(gh_token, gh_repo, pdf_bytes, f"itinerari/output_{nome_base}.pdf", f"Salvataggio PDF: {nome_base}")
        
        print(f"🔊 Esportazione Audio TTS per '{nome_config}'...")
        audio_bytes = genera_audio_multivoce(stringa_discussione, agenti_data)
        salva_file_su_github(gh_token, gh_repo, audio_bytes, f"audio/discussione_{nome_base}.mp3", f"Salvataggio Audio: {nome_base}")
        
        print(f"🔥 Processo di sincronizzazione per '{nome_config}' ultimato con successo!")
        
    except Exception as e:
        print(f"Errore critico nel thread asincrono: {e}")

# ----------------------------------------------------------------------
# INTERFACCIA UTENTE (STREAMLIT DASHBOARD)
# ----------------------------------------------------------------------

def get_secret(key_name):
    return st.secrets.get(key_name, os.getenv(key_name, ""))

gemini_key = get_secret("GEMINI_API_KEY")
serper_key = get_secret("SERPER_API_KEY")
github_token = get_secret("GITHUB_TOKEN")
github_repo = get_secret("GITHUB_REPO")

if not gemini_key or not github_token or not github_repo:
    st.error("❌ Errore: Mancano configurazioni critiche nei Secrets di Streamlit!")
    st.stop()

if "configs_salvate" not in st.session_state:
    with st.spinner("🔄 Allineamento configurazioni con GitHub..."):
        st.session_state.configs_salvate = carica_configurazioni_da_github(github_token, github_repo)

if "roster_personaggi" not in st.session_state:
    st.session_state.roster_personaggi = carica_personaggi_da_github(github_token, github_repo)

st.title("🤖 Agenzia Multi-Agente Universale V2: Tavola Rotonda Psicologica")
st.write("Simulatore di consigli decisionali decentralizzati con **Matrice di Fiducia** e **Roster Personaggi** indipendenti.")
st.markdown("---")

st.sidebar.header("🔄 Carica Modello Team")
opzioni_caricamento = ["Nuova Configurazione..."] + list(st.session_state.configs_salvate.keys())
config_scelta = st.sidebar.selectbox("Scegli un team preconfigurato:", opzioni_caricamento, index=0)

nome_configurazione = st.sidebar.text_input("ID/Nome della sessione attuale:", value="" if config_scelta == "Nuova Configurazione..." else config_scelta)
st.sidebar.markdown("---")

# --- GRIGLIA EDITING AGENTI & ROSTER ---
agenti_input = []
st.subheader("👤 Configurazione dei 4 Membri del Consiglio")

default_roles = ["Analista Strategico", "Esperto Tecnico", "Responsabile Operativo", "Facilitatore/Manager"]
col_a, col_b = st.columns(2)

for i in range(4):
    target_col = col_a if i < 2 else col_b
    with target_col:
        with st.expander(f"👤 Posizione Tavolo {i+1}", expanded=True):
            
            opzioni_roster = ["Nuovo Personaggio (Crea da zero)..."] + list(st.session_state.roster_personaggi.keys())
            index_default_sel = 0
            if config_scelta != "Nuova Configurazione..." and config_scelta in st.session_state.configs_salvate:
                try:
                    saved_agent_name = st.session_state.configs_salvate[config_scelta]["agenti"][i].get("name", "")
                    if saved_agent_name in st.session_state.roster_personaggi:
                        index_default_sel = opzioni_roster.index(saved_agent_name)
                except IndexError:
                    pass
            
            personaggio_scelto = st.selectbox(f"Seleziona Eroe per lo Slot {i+1}:", opzioni_roster, index=index_default_sel, key=f"sel_char_{i}")
            
            def_name = f"Agente {i+1}"
            def_role = default_roles[i]
            def_goal, def_back = "", ""
            def_weight = 0.5
            def_has_search = False
            
            if personaggio_scelto != "Nuovo Personaggio (Crea da zero)...":
                char_data = st.session_state.roster_personaggi[personaggio_scelto]
                def_name = char_data.get("name", def_name)
                def_role = char_data.get("role", def_role)
                def_goal = char_data.get("goal", "")
                def_back = char_data.get("backstory", "")
                def_weight = char_data.get("weight", 0.5)
                def_has_search = char_data.get("has_search", False)

            name = st.text_input(f"Nome dell'agente", value=def_name, key=f"n_{i}")
            role = st.text_input(f"Incarico / Ruolo operativo", value=def_role, key=f"r_{i}")
            goal = st.text_input(f"Target / Focus dell'agente", value=def_goal, key=f"g_{i}")
            backstory = st.text_area(f"Tratti psicologici e background", value=def_back, key=f"b_{i}", height=75)
            
            col_w, col_s = st.columns([2, 1])
            with col_w:
                weight = st.slider(f"Fermezza Voto (Weight)", 0.0, 1.0, value=def_weight, step=0.1, key=f"w_{i}")
            with col_s:
                st.write("")
                has_search = st.checkbox("📶 Ricerca Web", value=def_has_search, key=f"s_{i}", help="Se attivo, l'agente userà internet.")

            if st.button(f"💾 Inserisci {name} nel Roster globale", key=f"btn_save_char_{i}"):
                if name.strip() == "" or name.startswith("Agente"):
                    st.error("❌ Assegna un nome proprio valido prima di inserire il personaggio nel Roster!")
                else:
                    char_payload = {"name": name, "role": role, "goal": goal, "backstory": backstory, "weight": weight, "has_search": has_search}
                    char_json = json.dumps(char_payload, indent=4)
                    path_char_json = f"characters/{name.lower().replace(' ', '_')}.json"
                    
                    if salva_file_su_github(github_token, github_repo, char_json, path_char_json, f"Add Character: {name}"):
                        st.success(f"✨ Personaggio {name} salvato!")
                        st.session_state.roster_personaggi = carica_personaggi_da_github(github_token, github_repo)
                        st.rerun()

        st.markdown("---")
        agenti_input.append({"name": name, "role": role, "goal": goal, "backstory": backstory, "weight": weight, "has_search": has_search})

# --- SEZIONE MATRICE DI FIDUCIA E PROFILI DINAMICI ---
st.markdown("---")
col_m, col_p = st.columns([2, 3])
nomi_validi = [a['name'] for a in agenti_input if a['name']]

with col_m:
    st.subheader("📊 Matrice di Fiducia Incrociata")
    matrice_df = pd.DataFrame(index=nomi_validi, columns=nomi_validi)
    dati_matrice_salvati = {}
    
    if config_scelta != "Nuova Configurazione..." and config_scelta in st.session_state.configs_salvate:
        dati_matrice_salvati = st.session_state.configs_salvate[config_scelta].get("matrice_fiducia", {})

    for r in nomi_validi:
        for c in nomi_validi:
            if r == c:
                matrice_df.loc[r, c] = 100
            else:
                matrice_df.loc[r, c] = dati_matrice_salvati.get(r, {}).get(c, 70)

    matrice_editabile = st.data_editor(
        matrice_df,
        hide_index=False,
        column_config={col: st.column_config.NumberColumn(format="%d") for col in nomi_validi},
        key="matrice_editor"
    )

with col_p:
    st.subheader("🧠 Analisi Psicologiche verso i Colleghi")
    profili_psicologici_input = []
    dati_profili_salvati = []
    
    if config_scelta != "Nuova Configurazione..." and config_scelta in st.session_state.configs_salvate:
        dati_profili_salvati = st.session_state.configs_salvate[config_scelta].get("profili_psicologici", [])

    for i, analista_nome in enumerate(nomi_validi):
        with st.expander(f"🧠 Diario di {analista_nome}", expanded=(i==0)):
            mio_profilo = {"analista": analista_nome, "analisi": {}}
            mio_dati_salvato = {}
            
            for p in dati_profili_salvati:
                if p['analista'].lower() == analista_nome.lower():
                    mio_dati_salvato = p.get('analisi', {})
                    break

            for target_nome in nomi_validi:
                if analista_nome == target_nome:
                    continue
                def_analisi = mio_dati_salvato.get(target_nome, "Tende a...")
                analisi_txt = st.text_area(f"Analisi strategica verso {target_nome}", value=def_analisi, key=f"p_{analista_nome}_{target_nome}", height=65)
                mio_profilo["analisi"][target_nome] = analisi_txt
            
            profili_psicologici_input.append(mio_profilo)

# --- PULSANTE SALVA TAVOLO ---
st.markdown("---")
if st.button("💾 Archivia Modello Struttura Tavolo su GitHub"):
    if not nome_configurazione:
        st.error("❌ Manca il nome identificativo della configurazione!")
    else:
        payload = {
            "nome": nome_configurazione, 
            "agenti": agenti_input,
            "matrice_fiducia": matrice_editabile.to_dict(orient='index'),
            "profili_psicologici": profili_psicologici_input
        }
        json_content = json.dumps(payload, indent=4)
        path_json = f"config/{nome_configurazione.lower().replace(' ', '_')}.json"
        
        with st.spinner("💾 Committing in corso..."):
            if salva_file_su_github(github_token, github_repo, json_content, path_json, f"Update config: {nome_configurazione}"):
                st.success("Configurazione del Tavolo allineata con successo!")
                st.session_state.configs_salvate = carica_configurazioni_da_github(github_token, github_repo)

# --- RUN CRON PROMPT ---
st.markdown("---")
st.subheader("🚀 Lancio della Sessione Operativa")
task_prompt = st.text_area("Inserisci la direttiva o l'itinerario da ottimizzare:", 
                           "Pianificate nei dettagli l'itinerario di 21 giorni per Corea del Sud e Giappone Meridionale (Shikoku/Kyushu) ottimizzando i costi ed evitando buchi logistici.")

max_giri = st.slider("Cicli di revisione concessi (Loop Breaker):", min_value=3, max_value=20, value=12)

if st.button("🔥 Avvia Consiglio di Fazione in Background", type="primary"):
    if not nome_configurazione or len(nomi_validi) < 4:
        st.error("❌ Configurazione incompleta. Verifica i nomi dei 4 agenti e l'ID sessione.")
    else:
        args_background = (
            gemini_key, serper_key, github_token, github_repo, nome_configurazione, 
            agenti_input, matrice_editabile, profili_psicologici_input, task_prompt, max_giri
        )
        thread = threading.Thread(target=esegui_agenti_background, args=args_background)
        thread.start()
        st.success("⚡ Riunione delegata in background! Controlla la repo GitHub tra pochi minuti per ritirare PDF e MP3.")

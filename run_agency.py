import os
import json
import pandas as pd
from app import esegui_agenti_background, carica_configurazioni_da_github

def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    serper_key = os.getenv("SERPER_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPO")
    
    if not all([gemini_key, github_token, github_repo]):
        print("❌ Errore di sincronizzazione: Variabili ambientali obbligatorie non popolate.")
        return

    print("🔄 Estrazione in corso dei modelli JSON da GitHub...")
    configs = carica_configurazioni_da_github(github_token, github_repo)
    
    if not configs:
        print("ℹ️ Nessun modello JSON trovato nella cartella /config.")
        return

    for nome_config, data in configs.items():
        print(f"\n🚀 Wake-up automatico del team per il tavolo: {nome_config}")
        
        agenti_input = data.get("agenti", [])
        dati_matrice = data.get("matrice_fiducia", {})
        dati_profili = data.get("profili_psicologici", [])
        
        matrice_df = pd.DataFrame.from_dict(dati_matrice, orient='index')
        
        task_prompt = (
            "Esegui la sessione quotidiana di debriefing e allineamento sul piano d'azione corrente. "
            "Identificate margini di miglioramento ed eseguite una Tavola Rotonda finale per inserire una gemma nascosta."
        )
        
        max_giri = 12

        esegui_agenti_background(
            gemini_key, 
            serper_key, 
            github_token, 
            github_repo, 
            nome_config, 
            agenti_input, 
            matrice_df, 
            dati_profili, 
            task_prompt, 
            max_giri
        )
        print(f"✅ Tavolo '{nome_config}' sincronizzato con successo.")

if __name__ == "__main__":
    main()

# NIRO Content Pipeline

## Deine Aufgabe
1. Scrappe via Apify die gewünschten Plattformen
2. Analysiere virale Posts
3. Generiere den Content Plan als JSON-Array
4. Speichere das JSON unter: data/content_plan_raw.json
5. Führe danach automatisch aus: python pipeline.py data/content_plan_raw.json "KUNDENNAME"

## Output-Format (data/content_plan_raw.json)
Jeder Eintrag MUSS folgende Keys haben:
- week (int)
- week_theme (string)
- day (string, z.B. "Montag")
- platform (array of strings)
- format (string)
- topic (string)
- hook (string)
- caption (string)
- hashtags (array of strings)
- best_time (string, z.B. "07:00–08:00")
- target_audience (string)

## Nach der Pipeline
Streamlit App zeigt das Ergebnis automatisch an.
Starte Streamlit falls noch nicht aktiv: streamlit run app.py

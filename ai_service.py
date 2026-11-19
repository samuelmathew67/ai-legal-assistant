import os
import json
from dotenv import load_dotenv

# Load GEMINI_API_KEY from .env using override=True
load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Path to disk-backed response cache
CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache.json")

# In-memory dictionary cache loaded from cache.json on startup
RESPONSE_CACHE = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            RESPONSE_CACHE = json.load(f)
        print(f"[CACHE] Loaded {len(RESPONSE_CACHE)} cached responses from cache.json")
    except Exception as e:
        print(f"[CACHE] Error loading cache.json: {e}")
        RESPONSE_CACHE = {}

# Model order: low-latency, high-quota models first
MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash"
]


def generate_fallback_breakdown(query: str, sections: list) -> str:
    """
    Immediately formats and returns a clean plain-text breakdown directly from
    the local statutory JSON dataset so the frontend always receives a valid response.
    """
    if not sections:
        return (
            "No specific Indian statutory provisions matched your search terms.\n\n"
            "Educational Guidance:\n"
            "- For criminal offenses, refer to Bharatiya Nyaya Sanhita (BNS 2023) or the Indian Penal Code (IPC).\n"
            "- For cyber offenses (hacking, phishing, online fraud), refer to the Information Technology Act, 2000.\n"
            "- In case of emergency or immediate cyber theft, report to cybercrime.gov.in or dial helpline 1930."
        )

    lines = [
        f"Statutory Legal Breakdown for: \"{query}\"\n",
        "Retrieved Provisions from Statutory Database:\n"
    ]
    for idx, sec in enumerate(sections, 1):
        act = sec.get("act", "Indian Law")
        section = sec.get("section", "N/A")
        title = sec.get("title", "")
        desc = sec.get("description", "")
        mapping = sec.get("ipc_bns_mapping", "N/A")
        punish = sec.get("punishment", "Refer to Code schedule for sentencing.")

        lines.append(
            f"{idx}. {act} - {section}: {title}\n"
            f"   - Statutory Definition: {desc}\n"
            f"   - BNS / IPC Transition: {mapping}\n"
            f"   - Prescribed Punishment: {punish}\n"
        )

    lines.append(
        "Reporting & Legal Redressal: File an FIR at your local police station or report cybercrimes at https://cybercrime.gov.in (Helpline: 1930 / All Emergency: 112)."
    )
    return "\n".join(lines)


def analyze_with_gemini(query: str, sections: list) -> tuple[str, str]:
    """
    Analyzes user query against ONLY the relevant retrieved sections:
    1. Checks disk-backed RESPONSE_CACHE for instant 0-latency response.
    2. Runs configured genai.Client with timeout=25000 and attempts=1 (no slow retries).
    3. Runs model order: gemini-3.1-flash-lite -> gemini-3.5-flash-lite -> gemini-3.8-flash.
    4. On live Gemini success, updates RESPONSE_CACHE and writes cache.json to disk.
    5. If all models fail, immediately returns local statutory JSON breakdown.
    """
    query_key = query.strip().lower()

    # 1. Disk-backed response cache check
    if query_key in RESPONSE_CACHE:
        cached = RESPONSE_CACHE[query_key]
        if isinstance(cached, (list, tuple)) and len(cached) == 2:
            return cached[0], f"{cached[1]} (Cached)"
        elif isinstance(cached, str):
            return cached, "Gemini (Cached)"

    if not sections:
        return (
            "No statutory sections matched the query keywords. "
            "Please try searching with specific legal terms like 'theft', 'fraud', '420', 'hacking', or 'defamation'.",
            "Statutory Filter"
        )

    # Format relevant sections as clean context
    sections_context = json.dumps([
        {
            "act": s.get("act"),
            "section": s.get("section"),
            "title": s.get("title"),
            "description": s.get("description"),
            "bns_ipc_mapping": s.get("ipc_bns_mapping"),
            "punishment": s.get("punishment")
        } for s in sections
    ], indent=2)

    system_instruction = (
        "You are an Indian Legal Information Assistant. "
        "Summarize ONLY the provided Indian statutory sections in plain English. "
        "CRITICAL: Analyze the user scenario against ONLY the relevant retrieved sections. "
        "Explicitly ignore any retrieved section that does not fit the user's scenario. "
        "Do not invent laws. Always maintain an educational, non-advisory tone."
    )

    prompt = (
        f"User Query / Scenario: \"{query}\"\n\n"
        f"Retrieved Indian Statutory Sections:\n{sections_context}\n\n"
        "Instructions:\n"
        "1. Evaluate each retrieved section against the user's specific scenario. If a section is irrelevant or does not apply, explicitly ignore it.\n"
        "2. For the section(s) that genuinely fit, explain what the law states in simple, plain English.\n"
        "3. Highlight both the IPC section and its corresponding Bharatiya Nyaya Sanhita (BNS) reference, or IT Act provision.\n"
        "4. Conclude with educational procedural guidance (reporting at police station, cybercrime.gov.in, helpline 1930)."
    )

    # 2. Call Gemini using google-genai SDK (timeout=25000, attempts=1, system_instruction only)
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types

            http_opts = types.HttpOptions(
                timeout=25000,
                retry_options=types.HttpRetryOptions(attempts=1)
            )
            client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts)

            for model_name in MODELS:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction
                        )
                    )
                    if response and response.text:
                        display_name = model_name.replace("-", " ").title()
                        # Save live response to in-memory cache and write to disk (cache.json)
                        RESPONSE_CACHE[query_key] = [response.text, display_name]
                        try:
                            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                                json.dump(RESPONSE_CACHE, f, indent=2, ensure_ascii=False)
                        except Exception as e_disk:
                            print(f"[CACHE] Error writing cache.json: {e_disk}")

                        return response.text, display_name
                except Exception as e_model:
                    print(f"[API ERROR] Model {model_name} failed: {e_model}")
        except Exception as e_client:
            print(f"[API ERROR] Gemini client initialization failed: {e_client}")

    # 3. Instant local fail-safe: format and return matched sections cleanly in plain text
    fallback_summary = generate_fallback_breakdown(query, sections)
    return fallback_summary, "Local Statutory Database (Fallback)"

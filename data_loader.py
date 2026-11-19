import os
import re
import json
import requests

# In-memory statutory cache optimized for minimal RAM & sub-millisecond retrieval
STATUTORY_CACHE = []

# Common stopwords to ignore during retrieval scoring
STOPWORDS = {
    "someone", "my", "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been", "have",
    "has", "had", "do", "does", "did", "i", "me", "we", "our", "you", "your",
    "he", "she", "it", "they", "them", "this", "that", "what", "which", "who",
    "how", "can", "could", "will", "would", "about", "into", "any", "some",
    "section", "sec", "act", "law", "under", "tell", "please"
}

# Lightweight synonym mapping for colloquial terms to statutory language
SYNONYMS = {
    "stole": ["theft", "stolen"],
    "stolen": ["theft", "stolen"],
    "theft": ["theft", "stolen"],
    "scam": ["cheating", "fraud"],
    "fraud": ["cheating", "fraud"],
    "cheated": ["cheating", "cheat"],
    "hacked": ["hacking", "hack"],
    "murdered": ["murder", "death"],
    "killed": ["murder", "death"],
    "defamed": ["defamation"],
    "threatened": ["intimidation", "threat"],
    "assaulted": ["hurt", "assault"]
}

# Lightweight BNS concordance mapping
BNS_MAPPING = {
    "302": "BNS Section 103(1) (Punishment for Murder)",
    "307": "BNS Section 109 (Attempt to Murder)",
    "378": "BNS Section 303(1) (Theft)",
    "379": "BNS Section 303(2) (Punishment for Theft)",
    "380": "BNS Section 305 (Theft in dwelling house)",
    "415": "BNS Section 318(1) (Cheating)",
    "420": "BNS Section 318(4) (Cheating & Dishonestly Inducing Delivery of Property)",
    "405": "BNS Section 316(1) (Criminal Breach of Trust)",
    "406": "BNS Section 316(2) (Punishment for Criminal Breach of Trust)",
    "323": "BNS Section 115(2) (Voluntarily Causing Hurt)",
    "324": "BNS Section 118(1) (Hurt by dangerous weapon)",
    "354": "BNS Section 74 (Assault/Force to Outrage Modesty of Woman)",
    "354C": "BNS Section 77 (Voyeurism)",
    "354D": "BNS Section 78 (Stalking)",
    "363": "BNS Section 137(2) (Punishment for Kidnapping)",
    "376": "BNS Section 64 (Punishment for Rape)",
    "498A": "BNS Section 85 & 86 (Cruelty by Husband or Relatives)",
    "499": "BNS Section 356(1) (Defamation)",
    "500": "BNS Section 356(2) (Punishment for Defamation)",
    "503": "BNS Section 351(1) (Criminal Intimidation)",
    "506": "BNS Section 351(2) (Punishment for Criminal Intimidation)",
    "124A": "BNS Section 152 (Acts Endangering Sovereignty)",
    "141": "BNS Section 189 (Unlawful Assembly)",
    "279": "BNS Section 281 (Rash Driving)"
}

# Key IT Act cyber provisions
IT_SECTIONS = [
    {
        "act": "Information Technology Act, 2000",
        "section": "Section 66D",
        "title": "Cheating by personation by using computer resource (UPI / Online Scam)",
        "description": "Punishment for cheating by personation using any communication device or computer resource, phishing, or financial identity fraud.",
        "punishment": "Imprisonment up to 3 years and fine up to 1 lakh rupees.",
        "ipc_bns_mapping": "BNS Section 318(4) / IPC Section 420"
    },
    {
        "act": "Information Technology Act, 2000",
        "section": "Section 66",
        "title": "Computer related offences (Hacking and Unauthorized Access)",
        "description": "Dishonestly or fraudulently accessing, downloading, damaging, or disrupting computer systems or data.",
        "punishment": "Imprisonment up to 3 years or fine up to 5 lakh rupees, or both.",
        "ipc_bns_mapping": "BNS Section 324 (Mischief to data)"
    },
    {
        "act": "Information Technology Act, 2000",
        "section": "Section 66C",
        "title": "Punishment for identity theft",
        "description": "Fraudulently or dishonestly making use of electronic signature, password, or unique identification feature of any person.",
        "punishment": "Imprisonment up to 3 years and fine up to 1 lakh rupees.",
        "ipc_bns_mapping": "BNS Section 319 / IPC Section 419"
    },
    {
        "act": "Information Technology Act, 2000",
        "section": "Section 66E",
        "title": "Punishment for violation of privacy",
        "description": "Intentionally capturing, publishing, or transmitting images of private area of a person without consent.",
        "punishment": "Imprisonment up to 3 years or fine up to 2 lakh rupees, or both.",
        "ipc_bns_mapping": "BNS Section 77 / IPC Section 354C"
    },
    {
        "act": "Information Technology Act, 2000",
        "section": "Section 67",
        "title": "Publishing or transmitting obscene material in electronic form",
        "description": "Publishing or transmitting lascivious material or vulgar harassment messages in electronic form.",
        "punishment": "Imprisonment up to 3 years and fine up to 5 lakh rupees.",
        "ipc_bns_mapping": "BNS Section 294 / IPC Section 292"
    }
]

def load_statutory_data():
    """
    Fetches full IPC JSON, stores minimal strings to conserve RAM,
    and pre-indexes lowercase token sets once on startup for instant retrieval.
    """
    global STATUTORY_CACHE
    url = "https://raw.githubusercontent.com/civictech-India/Indian-Law-Penal-Code-Json/master/ipc.json"
    cache_file = os.path.join(os.path.dirname(__file__), "ipc_cache.json")
    items = []

    print("[DATA LOADER] Fetching statutory data from GitHub...")
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            raw_ipc = resp.json()
            items = raw_ipc
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(raw_ipc, f)
            print(f"[DATA LOADER] Successfully downloaded {len(raw_ipc)} IPC sections from GitHub.")
    except Exception as e:
        print(f"[DATA LOADER] GitHub fetch failed ({e}). Checking local cache file...")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                items = json.load(f)
            print(f"[DATA LOADER] Loaded {len(items)} sections from local cache.")

    # Reusable constant strings to minimize memory allocations
    default_act = "Indian Penal Code, 1860"
    default_punish = "Refer to Code schedule for exact sentencing."

    STATUTORY_CACHE = []
    # Index IPC sections
    for item in items:
        sec_num = str(item.get("Section", "")).strip()
        title = item.get("section_title", "").strip()
        desc = item.get("section_desc", "").strip()
        bns_info = BNS_MAPPING.get(sec_num, f"Refer to BNS concordance for IPC {sec_num}")

        STATUTORY_CACHE.append({
            "act": default_act,
            "section": f"Section {sec_num}",
            "title": title,
            "description": desc,
            "punishment": default_punish,
            "ipc_bns_mapping": bns_info,
            "_sec_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", f"{sec_num} {bns_info}".lower())) - STOPWORDS,
            "_title_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", title.lower())) - STOPWORDS,
            "_desc_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", desc.lower())) - STOPWORDS
        })

    # Index IT Act sections
    for it in IT_SECTIONS:
        STATUTORY_CACHE.append({
            **it,
            "_sec_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", f"{it['section']} {it['ipc_bns_mapping']}".lower())) - STOPWORDS,
            "_title_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", it["title"].lower())) - STOPWORDS,
            "_desc_kw": set(re.findall(r"\b[a-zA-Z0-9]+\b", it["description"].lower())) - STOPWORDS
        })

    print(f"[DATA LOADER] Ready. Pre-indexed {len(STATUTORY_CACHE)} statutory sections in memory.")


def retrieve_top_sections(query: str, k: int = 3):
    """
    Sub-millisecond retrieval using pre-indexed lowercase token sets.
    ONLY returns sections with score > 0 (strictly zero padding).
    """
    raw_tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9]+\b", query)]
    clean_tokens = [t for t in raw_tokens if t not in STOPWORDS and len(t) > 1]
    if not clean_tokens:
        clean_tokens = raw_tokens

    # Expand tokens using pre-mapped statutory synonyms
    expanded_tokens = list(clean_tokens)
    for t in clean_tokens:
        if t in SYNONYMS:
            expanded_tokens.extend(SYNONYMS[t])

    scored_items = []
    for statute in STATUTORY_CACHE:
        score = 0
        sec_kw = statute["_sec_kw"]
        title_kw = statute["_title_kw"]
        desc_kw = statute["_desc_kw"]

        for token in expanded_tokens:
            if token in sec_kw:
                score += 50
            if token in title_kw:
                score += 15
            if token in desc_kw:
                score += 3

        if score > 0:
            scored_items.append((score, statute))

    # Sort descending by score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # Return ONLY sections with score > 0, capped at k (excluding internal set fields for clean JSON serialization)
    results = []
    for _, item in scored_items[:k]:
        results.append({k: v for k, v in item.items() if not k.startswith("_")})
    return results

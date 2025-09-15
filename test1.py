#!/usr/bin/env python3
# Minimal test.py with logging + error catching

import json, gc, sys, logging
from tqdm import tqdm
from langchain.text_splitter import RecursiveCharacterTextSplitter
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from llama_cpp import Llama

# --- CONFIG ---
JSON_PATH = "/home/anand/Documents/data/youtube_search_output549894.json"
GGUF_PATH = "/home/anand/Downloads/phi4.gguf"
OUT_JSON = "analysis_results.json"

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --- Utils ---
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON: {e}")
        sys.exit(1)

def extract_texts(data):
    texts = []
    for e in data:
        if e.get("transcript"): texts.append(e["transcript"])
        for c in e.get("comments", []):
            if c.get("text"): texts.append(c["text"])
            for sc in c.get("subcomments", []):
                if sc.get("text"): texts.append(sc["text"])
    return texts

def chunk_texts(texts, size=500, overlap=50):
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    return [d.page_content for d in splitter.create_documents(texts)]

def is_english(txt):
    return sum(1 for c in txt if ord(c) < 128)/max(1,len(txt)) > 0.9

# --- Translation ---
def translate(chunks):
    try:
        tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        model = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        trans = pipeline("translation", model=model, tokenizer=tok)
    except Exception as e:
        logging.error(f"Failed to load translation model: {e}")
        return chunks  # fallback

    out = []
    for c in tqdm(chunks, desc="Translating"):
        try:
            if is_english(c): out.append(c)
            else: out.append(trans(c, max_length=512)[0]["translation_text"])
        except Exception as e:
            logging.warning(f"Translation failed for chunk: {e}")
            out.append(c)  # fallback keep original
    return out

# --- Phi4 ---
def load_phi4(path):
    try:
        llm = Llama(model_path=path, n_ctx=2048, n_threads=4, n_gpu_layers=0, verbose=False)
        return llm
    except Exception as e:
        logging.error(f"Failed to load Phi-4 model: {e}")
        sys.exit(1)

def ask(llm, prompt, max_tokens=256):
    try:
        r = llm(prompt, max_tokens=max_tokens, echo=False)
        return r["choices"][0]["text"].strip()
    except Exception as e:
        logging.error(f"LLM call failed: {e}")
        return "ERROR"

# --- Pipeline ---
def summarize_windows(llm, chunks, wsize=6, step=6):
    summaries = []
    for i in tqdm(range(0,len(chunks),step), desc="Summarizing"):
        try:
            w = chunks[i:i+wsize]
            if not w: continue
            text = "\n\n".join(w)
            s = ask(llm, f"Summarize into 2-3 bullet points:\n\n{text}\n\nBullets:\n", 200)
            summaries.append(s)
        except Exception as e:
            logging.warning(f"Summarization failed at window {i}: {e}")
            summaries.append("ERROR")
    return summaries

def extract_claims(llm, summaries):
    claims = []
    for s in tqdm(summaries, desc="Claims"):
        try:
            out = ask(llm, f"Extract key claims (one per line):\n{s}\n\nClaims:\n", 150)
            claims.extend([l for l in out.splitlines() if l.strip()])
        except Exception as e:
            logging.warning(f"Claim extraction failed: {e}")
    return claims

def explain_claims(llm, claims, chunks):
    results=[]
    for c in tqdm(claims, desc="Explanations"):
        try:
            ctx = "\n".join(chunks[:3])  # simple: just first 3 chunks (debug mode)
            out = ask(llm, f"Claim: {c}\nContext:\n{ctx}\n\nExplain in 2-3 sentences:\n", 200)
            results.append({"claim":c,"explanation":out})
        except Exception as e:
            logging.warning(f"Explanation failed for claim {c[:30]}...: {e}")
            results.append({"claim":c,"explanation":"ERROR"})
    return results

def merge_story(llm, explained, group_size=8):
    try:
        parts = []
        # step 1: split into groups
        for start in range(0, len(explained), group_size):
            group = explained[start:start+group_size]
            join_text = "\n".join([f"{e['claim']}\n{e['explanation']}" for e in group])
            out = ask(llm, f"Write a short narrative (1-2 paragraphs) from these claims:\n\n{join_text}\n\nStory:\n", 400)
            parts.append(out)

        # step 2: merge partials
        if len(parts) > 1:
            final_input = "\n\n".join(parts)
            final = ask(llm, f"Combine these partial narratives into a single coherent final story (2-3 paragraphs):\n\n{final_input}\n\nFinal Story:\n", 400)
            return final
        return parts[0] if parts else "ERROR: no story"
    except Exception as e:
        logging.error(f"Final merge failed: {e}")
        return "ERROR: Story merge failed"


# --- MAIN ---
def main():
    try:
        data = load_json(JSON_PATH)
        texts = extract_texts(data)
        chunks = chunk_texts(texts)
        logging.info(f"Texts: {len(texts)}, Chunks: {len(chunks)}")

        translated = translate(chunks)
        logging.info("Translation complete")

        llm = load_phi4(GGUF_PATH)
        logging.info("Phi-4 model loaded")

        summaries = summarize_windows(llm, translated)
        logging.info(f"Generated {len(summaries)} summaries")

        claims = extract_claims(llm, summaries)
        logging.info(f"Extracted {len(claims)} claims")

        explained = explain_claims(llm, claims, translated)
        logging.info(f"Explained {len(explained)} claims")

        story = merge_story(llm, explained)
        logging.info("Global story built")

        report = {"summaries":summaries,"claims":explained,"story":story}
        with open(OUT_JSON,"w",encoding="utf-8") as f: json.dump(report,f,indent=2,ensure_ascii=False)

        print("\n===== FINAL STORY =====\n")
        print(story)

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__=="__main__":
    main()


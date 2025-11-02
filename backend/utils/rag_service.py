"""
RAG (Retrieval-Augmented Generation) Service
--------------------------------------------
Retrieves relevant snippets or documents from local knowledge sources
to provide context for the LLM.

Enhanced for the Instalilly Appliance Assistant:
- Weighted keyword search for brand/category
- Dynamic appliance context for prompts
- Intent classification for better prompt control
- Structured prompt builder for LLM
"""

import os
import glob
import logging
from typing import List, Tuple, Dict
from bs4 import BeautifulSoup

log = logging.getLogger("backend")

# --- Define Project Root ---
# __file__ is the absolute path to this file (rag_service.py)
# os.path.dirname(__file__) is the .../backend/utils directory
# We go up two levels ('..', '..') to get the absolute project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Construct absolute paths for data and the knowledge base
# This is now robust and will work regardless of where the script is run
DEFAULT_HTML_PATH = os.path.join(PROJECT_ROOT, "data", "*.html")
DEFAULT_KNOWLEDGE_PATH = os.path.join(PROJECT_ROOT, "knowledge_base.txt")
# --- End ---


class RAGService:
    """
    Lightweight RAG layer for the Appliance Assistant.
    Uses keyword scoring + similarity fallback.
    """

    def __init__(self, html_glob_path: str = DEFAULT_HTML_PATH, knowledge_path: str = DEFAULT_KNOWLEDGE_PATH):
        """
        Initializes the RAG service.

        Args:
            html_glob_path (str): The glob pattern to find your source HTML files.
                                  Defaults to an absolute path to the project's 'data' folder.
            knowledge_path (str): The path to save the combined text corpus.
                                  Defaults to the project root.
        """
        self.knowledge_path = knowledge_path

        # ✅ Compile all HTML files into a single KB text file
        #    We look in the absolute path specified by html_glob_path
        html_files = glob.glob(html_glob_path)
        log.info(f"Found {len(html_files)} HTML files with pattern '{html_glob_path}': {html_files}")

        corpus = []
        if not html_files:
             log.warning(f"No HTML files found at '{html_glob_path}'. RAG will be empty unless '{knowledge_path}' already exists.")
        
        for f in html_files:
            try:
                with open(f, "r", encoding="utf-8") as h:
                    soup = BeautifulSoup(h, "html.parser")
                    # Find the main content, or fall back to the whole body
                    # This is a guess; you may need to refine the selector for PartSelect
                    main_content = soup.find("main") or soup.find("body")
                    if main_content:
                        text = main_content.get_text(separator=" ", strip=True)
                        corpus.append(text)
                        log.info(f"Successfully parsed '{f}'")
                    else:
                        log.warning(f"Could not find <main> or <body> in '{f}'")
            except Exception as e:
                log.error(f"Error parsing file {f}: {e}")

        # Only write to the knowledge base if we successfully parsed new files
        if corpus:
            # We use the absolute path for the knowledge base as well
            os.makedirs(os.path.dirname(knowledge_path), exist_ok=True)
            with open(knowledge_path, "w", encoding="utf-8") as out:
                out.write("\n\n".join(corpus))
            log.info(f"Successfully wrote {len(corpus)} documents to '{knowledge_path}'")

        # ✅ Load into memory
        self.docs: List[str] = []
        if os.path.exists(knowledge_path):
            with open(knowledge_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
                # Split by double newline, and filter out any empty strings
                self.docs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not self.docs:
             log.warning(f"RAGService is empty. No documents loaded from '{knowledge_path}'.")
        else:
            log.info(f"✅ RAGService initialized with {len(self.docs)} docs.")

    # ------------------------------------------------------------
    # 🧠 Intent Classification
    # ------------------------------------------------------------
    def classify_intent(self, query: str) -> str:
        """
        Basic intent classification.
        NOTE: Your log suggested you have a better ML-based
        classifier. You should use that one if possible.
        """
        q = query.lower()
        if any(word in q for word in ["compatible", "fit", "works with"]):
            return "compatibility"
        if any(word in q for word in ["how to", "replace", "install", "fix", "repair", "broken"]):
            return "repair_guide"
        if any(word in q for word in ["rack", "filter", "pump", "hose", "basket", "drawer", "bin", "ice maker"]):
            return "part_lookup"
        if any(word in q for word in ["clean", "maintain", "how often", "smell"]):
            return "maintenance"
        return "general_help"

    # ------------------------------------------------------------
    # 🔍 Weighted Keyword Search
    # ------------------------------------------------------------
    def search(self, query: str, appliance_context: str = "appliance", k: int = 5) -> List[str]:
        """
        Performs a weighted keyword search.
        
        Args:
            query (str): The user's search query.
            appliance_context (str): The appliance in focus (e.g., "dishwasher", "refrigerator").
            k (int): The number of documents to return.
        """
        if not self.docs:
            log.warning("⚠️ RAGService.search(): No documents available for retrieval.")
            return ["(Internal Error: No RAG documents loaded.)"]

        query_terms = query.lower().split()
        
        # Add appliance context as a high-weight term
        query_terms.append(appliance_context)

        # Dynamic weights based on context and common parts
        weights = {
            # Appliance context is most important
            "dishwasher": 3.0,
            "refrigerator": 3.0,
            
            # Common parts
            "rack": 1.8,
            "filter": 1.8,
            "drawer": 1.8,
            "bin": 1.8,
            "ice maker": 2.0,
            "pump": 1.5,
            "hose": 1.2,
            "basket": 1.2,

            # Brand
            "whirlpool": 2.5,
            "kenmore": 2.5,
            "maytag": 2.5,
            "lg": 2.5,
        }
        
        # Set the weight for the *current* appliance context even higher
        if appliance_context in weights:
            weights[appliance_context] = 5.0

        scores: List[Tuple[str, float]] = []
        for doc in self.docs:
            score = 0
            doc_lower = doc.lower()
            for term in query_terms:
                term_weight = weights.get(term, 1.0)
                score += doc_lower.count(term) * term_weight
            if score > 0:
                scores.append((doc, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        if not scores:
            scores = self._fallback_similarity(query)

        top_docs = [doc for doc, _ in scores[:k]]
        log.info(f"🔎 Retrieved {len(top_docs)} relevant docs for query '{query[:40]}...'")
        return top_docs

    # ------------------------------------------------------------
    # 🧠 Fallback Similarity (Jaccard)
    # ------------------------------------------------------------
    def _fallback_similarity(self, query: str) -> List[Tuple[str, float]]:
        query_set = set(query.lower().split())
        scores: List[Tuple[str, float]] = []
        for doc in self.docs:
            doc_set = set(doc.lower().split())
            inter = len(query_set & doc_set)
            union = len(query_set | doc_set)
            sim = inter / union if union else 0
            if sim > 0.05:
                scores.append((doc, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    # ------------------------------------------------------------
    # 🏗️ Structured Prompt Builder
    # ------------------------------------------------------------
    def build_prompt(self, user_query: str, retrieved_docs: List[str], chat_history: List[Dict[str, str]], appliance_context: str) -> str:
        """
        Builds a dynamic, structured prompt for the LLM.

        Args:
            user_query (str): The latest query from the user.
            retrieved_docs (List[str]): Context from the RAG search.
            chat_history (List[Dict[str, str]]): Previous conversation turns.
            appliance_context (str): The appliance being discussed (e.g., "dishwasher").
        """
        intent = self.classify_intent(user_query)
        context = "\n\n".join(retrieved_docs[:3]) if retrieved_docs else "(No context found)"

        # Build a simple history string
        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

        return f"""
# Role
You are Instalilly AI — a friendly and expert AI repair assistant for PartSelect.
You are currently helping a customer with their **{appliance_context.upper()}**.

# Objective
Help users find correct replacement parts, confirm part compatibility,
and get repair/installation guides for their appliance.

# Rules
- **STAY ON TOPIC:** Only answer about the user's **{appliance_context.upper()}**.
- **BE CONCISE:** Give clear, actionable answers. Do not overwhelm the user.
- **USE CONTEXT:** Base your answer *only* on the provided "Context" from the parts database.
- **PART NUMBERS:** When listing parts, always include the Part Number (e.g., PS11752778).
- **SAFETY FIRST:** For any installation or repair, *always* include a safety warning (e.g., "Before you begin, make sure to unplug your appliance and shut off the water supply.").

# Detected Intent: {intent}

# Conversation History
{history_str}

# Context (retrieved from parts database)
{context}

# User Query
{user_query}

# Expected Output
- **For 'part_lookup':** "Here are some parts that match your description: \n 1. [Part Name] (Part: [Part Number]) \n 2. ..."
- **For 'repair_guide':** "I can help with that! Here are the steps: \n [SAFETY WARNING] \n 1. [Step] \n 2. [Step]..."
- **For 'compatibility':** "Please provide both the Part Number and your appliance's Model Number so I can check for you." (Unless you can infer it from history).
- **If out of scope (e.g., user asks about a car):** Politely state that you can only help with **{appliance_context}** parts.
"""

    # ------------------------------------------------------------
    # 🧩 Utilities
    # ------------------------------------------------------------
    def add_document(self, text: str):
        """Add a document dynamically."""
        self.docs.append(text.strip())

    def size(self) -> int:
        """Return total number of knowledge chunks."""
        return len(self.docs)


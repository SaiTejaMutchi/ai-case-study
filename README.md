# 🧠 Appliance Assistant (AI Case Study)

An AI-powered **Appliance Parts Assistant** built with **FastAPI** (backend) and **React + Vite** (frontend).
It helps users discover compatible appliance parts, get repair guidance, and ask context-aware questions — powered by **Google Gemini**.

---

## 🚀 Quick Start

### 🧩 Requirements

| Tool                   | Version                |
| ---------------------- | ---------------------- |
| Python                 | 3.10 +                 |
| Node.js                | 18 +                   |
| npm                    | bundled with Node      |
| macOS / Linux Terminal | for running `setup.sh` |

---

### ⚙️ 1️⃣ Clone the Repository

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

---

### 🔑 2️⃣ Configure the Gemini API Key

The app requires a **Google Gemini API key** for backend LLM features.

#### ✅ Option 1 (Recommended): Use a `.env` file

```bash
cd backend
touch .env
```

Paste your key:

```bash
GEMINI_API_KEY=your_real_gemini_api_key_here
```

Then return to the root:

```bash
cd ..
```

> 💡 Use `backend/.env.example` as a reference.
> 🔒 This is the **safe** method — `.env` is ignored by Git and keeps your key private.

---

#### ⚠️ Option 2 (Not Safe): Hard-code the key (for local testing only)

Edit:

```
backend/utils/llm_gemini.py
```

Find:

```python
API_KEY = os.getenv("GEMINI_API_KEY")
```

and replace temporarily with:

```python
API_KEY = "your_real_gemini_api_key_here"
```



---

### 🧰 3️⃣ Run the Setup Script

From the project root:

```bash
chmod +x setup.sh
./setup.sh
```

This will automatically:

* create a Python virtual environment
* install backend requirements (`backend/requirements.txt`)
* install frontend dependencies (`frontend/package.json`)
* launch **FastAPI** and **Vite** in separate Terminal windows
* open the app in your browser → [http://localhost:5173](http://localhost:5173)

---

### 💻 4️⃣ Access the App

* **Frontend (UI):** [http://localhost:5173](http://localhost:5173)
* **Backend (API Docs):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

🎉 Both servers run in separate Terminal windows — backend and frontend.

---

## 🧱 Project Structure

```
case-study-main-updated/
│
├── backend/
│   ├── app.py
│   ├── utils/
│   │   └── llm_gemini.py      # Gemini API logic
│   ├── requirements.txt
│   ├── .env.example
│
├── frontend/
│   ├── src/
│   ├── vite.config.js
│   ├── package.json
│
├── setup.sh                   # One-click setup + launcher
├── README.md
└── .gitignore
```

---

## 🧩 Troubleshooting

| Issue                       | Fix                                                                             |
| --------------------------- | ------------------------------------------------------------------------------- |
| ❌ Port already in use       | `kill -9 $(lsof -ti :8000 :5173)` then rerun `./setup.sh`                       |
| ⚠️ `GEMINI_API_KEY` missing | Add to `backend/.env` or hard-code temporarily in `backend/utils/llm_gemini.py` |
| 🔒 Permission denied        | Run `chmod +x setup.sh` once                                                    |
| 🌐 Browser did not open     | Manually visit [http://localhost:5173](http://localhost:5173)                   |

---

## 🧠 Tech Stack

| Layer    | Technology                        |
| -------- | --------------------------------- |
| Frontend | React (Vite) + Tailwind           |
| Backend  | FastAPI (Python)                  |
| LLM      | Google Gemini 2.5 Flash           |
| Data     | HTML-based RAG ingestion          |
| Scripts  | Bash (automated setup & launcher) |

---

## 📄 License

MIT License © 2025 

---

```bash
git add .
git commit -m "Clean safe release: added setup launcher + updated README"
git push origin main
```

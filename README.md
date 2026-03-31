<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Lite Logo" width="50%"/>

# 🐟 MiroFish Lite
### The Next-Generation Evolution of Swarm Intelligence

[![MIT License](https://img.shields.io/badge/License-MIT-00FF88?style=for-the-badge&logo=opensourceinitiative&logoColor=black)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.x-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
[![Gemini](https://img.shields.io/badge/AI-Gemini_Flash-8E75E9?style=for-the-badge&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)

**MiroFish Lite** is a cost-optimized, cloud-ready rewrite of the original MiroFish swarm intelligence engine. It leverages advanced multi-agent simulations to predict complex social and market outcomes with high fidelity.

[Explore the Docs](#-key-features) • [Quick Start](#-one-click-setup) • [Meet the Developer](#-meet-the-developer)

</div>

---

## ⚡ The "Lite" Transformation

MiroFish Lite represents a complete architectural overhaul, focusing on developer productivity, operational cost-efficiency, and a premium user experience.

### 🏛️ Core Architectural Shift: Zep ⮕ Supabase
The most significant change was replacing the complex Zep memory service with **Supabase (PostgreSQL + PGVector)**. 
- **Legacy**: MiroFish originally depended on a self-hosted Zep instance, which was difficult and costly to maintain.
- **Lite**: Uses Supabase for built-in vector searches and relational data, drastically reducing setup friction and operational costs.

### 🎨 UI Overhaul: "Cyber Obsidian"
Experience a high-end, cyberpunk-inspired dark mode theme.
- **Design System**: Features deep charcoal backgrounds, neon cyan accents, glassmorphism effects, and premium typography (*Outfit/Inter*).
- **Smooth Workflow**: A simplified 5-step wizard guides you from graph extraction to real-time report generation and interactive Q&A.

### ⚙️ Hardened Simulation Engine
- **Deterministic Personas**: Refactored `OasisProfileGenerator` ensures agent behaviors are consistent and error-free.
- **Gemini Optimized**: Standardized on Google's Gemini models for high-quality, cost-efficient logic processing.
- **Live Monitoring**: Real-time log streaming from the backend allows you to watch agent interactions as they unfold.

---

## 🚀 One-Click Setup

We've removed the manual complexity. Setting up MiroFish Lite is now a single command.

### Prerequisites
- **Node.js 18+**
- **Python 3.11+**
- **Supabase Account** (for PGVector storage)

### Starting the Machine (Localhost)
To launch the entire system on your local machine, run the unified startup script:

```bash
# 1. Clone and enter the repository
git clone https://github.com/sidhardh-balaji/mirofish-lite.git
cd mirofish-lite

# 2. Set up your environment
cp .env.example .env
# Important: Edit .env with your GEMINI_API_KEY, SUPABASE_URL, and SUPABASE_KEY

# 3. Fire it up!
chmod +x start.sh
./start.sh
```

**What happens next?**
- **Backend**: Starts automatically on `http://localhost:5001`
- **Frontend**: Starts automatically on `http://localhost:5173` (or the next available port)
- **Live Logs**: Both services will stream their logs directly to your terminal.
- **Auto-Open**: On macOS, your default browser will automatically open the dashboard.

*The `start.sh` script handles dependency checks, environment validation, and launches both services in a single managed session.*

---

## 🔄 Intelligent Workflow

1.  **Graph Extraction**: Upload seed documents to build your simulation world.
2.  **Environment Setup**: Auto-generate agent personas and simulation parameters.
3.  **Real-Time Simulation**: Watch agents interact in a dynamic, temporal sandbox.
4.  **AI Reporting**: Receive a comprehensive, data-driven prediction report.
5.  **Interactive Q&A**: Chat directly with simulation agents or the analysis engine.

---

## 🛠️ Tech Stack

- **Frontend**: Vue 3 (Composition API), Vite, Cyber Obsidian Design System.
- **Backend**: Python (Flask), Supabase (PostgreSQL + PGVector).
- **AI Core**: Google Gemini, CAMEL-AI Oasis Engine.
- **Data Flow**: Real-time WebSocket log streaming.

---

## 👨‍💻 Meet the Developer

**MiroFish Lite** is developed and maintained by **Sidhardh Balaji**. If you're interested in multi-agent systems, AI simulations, or premium UI/UX, let's connect!

<div align="left">

[![Instagram](https://img.shields.io/badge/Instagram-Follow-E4405F?style=for-the-badge&logo=instagram&logoColor=white)](https://www.instagram.com/sidhardhsays/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/sidhardh-balaji/)

</div>

---

## 📄 License & Acknowledgments

- **License**: MIT
- **Strategic Support**: Incubated with support from **Shanda Group**.
- **Engine Core**: Powered by **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)**.

---

<div align="center">
  <sub>Built with ❤️ by Sidhardh Balaji</sub>
</div>

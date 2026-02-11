# SmartIntake

**AI-Assisted Patient Triage & Nurse Workflow Platform**

SmartIntake is a modern web application that streamlines medical intake and nurse triage workflows. It combines AI-powered symptom collection with human nurse oversight to provide safe, efficient patient screening.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastHTML](https://img.shields.io/badge/FastHTML-Latest-green.svg)](https://fastht.ml/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/license/mit)

---

## 🎯 Overview

SmartIntake bridges the gap between initial patient contact and professional medical care by:

- **Automated Intake**: AI-guided questionnaire collects structured symptom data
- **Intelligent Summarization**: Gemini AI generates concise clinical summaries for nurses
- **Smart Triage**: Automatic urgent case detection with nurse escalation
- **Session Management**: Two-tier timeout system with grace periods


### ⚠️ Important Disclaimer

**SmartIntake is a screening and triage tool, NOT a diagnostic or treatment platform.** All clinical decisions are made by qualified healthcare professionals. The AI assists with data collection and summarization only.

---

## ✨ Key Features

### For Patients (Beneficiaries)

- 📝 **Structured Intake**: Step-by-step symptom questionnaire
- 🚨 **Emergency Detection**: Automatic escalation for critical symptoms
- ⏰ **Session Persistence**: Resume inactive sessions within grace period (80 minutes)
- 📊 **History Access**: View past consultations and outcomes
- 💬 **Live Chat**: Real-time communication with nurses when needed

### For Nurses

- 🎯 **Smart Queue**: Prioritized patient list with urgent case highlighting
- 📋 **AI Summaries**: Gemini-generated intake summaries
- ✅ **Case Completion**: Formal closure workflow with required documentation
- 🔔 **Real-time Updates**: Auto-refreshing dashboard (HTMX polling)
- 📝 **Audit Trail**: Complete chat history for every interaction

### Technical Highlights

- ⚡ **FastHTML**: Modern Python web framework with HTMX
- 🎨 **MonsterUI**: Beautiful, accessible UI components
- 🤖 **Gemini AI**: Large language model for summarization
- 🗄️ **SQLite**: Lightweight, embedded database
- 🔐 **Secure Auth**: Bcrypt password hashing, session management
- ⏱️ **Two-Tier Timeout**: 20-minute soft timeout, 80-minute hard timeout

---

## 🏗️ Architecture

### Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastHTML (Starlette + HTMX) |
| **Frontend** | MonsterUI (Tailwind + DaisyUI) |
| **Database** | SQLite with MiniDataAPI |
| **AI Model** | Google Gemini (2.5 Flash / 2.0 Flash / 1.5 Flash) |
| **Auth** | Bcrypt + Session Middleware |
| **Deployment** | Uvicorn ASGI Server |

### Project Structure

```
SmartIntake/
├── app.py              # Main application & routes
├── models.py           # Data models & state machine
├── logic.py            # Business logic & AI integration
├── components.py       # UI components & layouts
├── database.py         # Database schema & middleware
├── auth.py             # Authentication & authorization
├── config.py           # Configuration & API keys
├── requirements.txt    # Python dependencies
├── static/            # Static assets (CSS, JS, images)
└── users.db           # SQLite database (auto-created)
```

### State Machine

Sessions progress through these states:

```
INTAKE → WAITING_FOR_NURSE → NURSE_ACTIVE → CLOSED/COMPLETED
   ↓                             ↓
URGENT ←────────────────────────┘
   ↓ (20 min inactivity)
INACTIVE
   ↓ (60 min grace period)
CLOSED
```

**Special Rules:**
- `URGENT` sessions **never** auto-timeout
- `INACTIVE` sessions can be seamlessly resumed within 80 minutes
- Only nurses can transition `URGENT` → `COMPLETED`

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Google Cloud account with Gemini API access
- Git

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/MrCzaro/SmartIntake.git
cd SmartIntake
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

Get your API key from: [Google AI Studio](https://makersuite.google.com/app/apikey)

5. **Initialize database**

The database will be created automatically on first run. The schema includes automatic migration for the `last_activity` column.

6. **Run the application**
```bash
python app.py
```

7. **Access the application**

Open your browser and navigate to: `http://localhost:5001`

---

## 📖 Usage Guide

### First-Time Setup

1. **Create Accounts**
   - Navigate to `/signup`
   - Create at least one **Nurse** account
   - Create at least one **Beneficiary** account

2. **Login & Role Selection**
   - Users are redirected based on their role:
     - Beneficiaries → `/beneficiary` (patient dashboard)
     - Nurses → `/nurse` (triage dashboard)

### Beneficiary Workflow

1. **Start Consultation** → Click "Start New Consultation"
2. **Answer Questions** → Complete the 11-question intake form
3. **AI Summary Generated** → Automatic Gemini summary created
4. **Wait for Nurse** → Session enters nurse queue
5. **Chat with Nurse** (optional) → Real-time messaging
6. **Session Closes** → Manual close or auto-timeout

**Emergency Features:**
- 🆘 button for immediate nurse escalation
- Automatic detection of keywords like "chest pain", "can't breathe"

### Nurse Workflow

1. **View Dashboard** → See all active cases
2. **Prioritize Urgent** → Urgent cases appear at top
3. **Review Summary** → Read AI-generated intake summary
4. **Join Session** → Click "Review" to enter chat
5. **Communicate** → Chat with patient if needed
6. **Complete Case** → Document and close (required for urgent cases)

**Dashboard Features:**
- Real-time updates every 3 seconds
- Urgent case counter badge
- Unread session highlighting
- Last symptom preview

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API key for AI summarization | Yes |

### Session Timeouts

Configurable in `logic.py`:

```python
# Soft timeout - session becomes INACTIVE
SOFT_TIMEOUT_MINUTES = 20

# Grace period - time to resume before permanent closure
GRACE_PERIOD_MINUTES = 60  # Total = 80 minutes
```

### Intake Questions

Customize questions in `models.py`:

```python
INTAKE_SCHEMA = [
    {"id": "chief_complaint", "q": "What is your main issue today?"},
    {"id": "location", "q": "Where is the problem located?"},
    {"id": "onset", "q": "When did it start?"},
    {"id": "severity", "q": "How severe is it from 1 to 10?"},
    {"id": "relieving_factors", "q": "What makes it better?"},
    {"id": "aggravating_factors", "q": "What makes it worse?"},
    {"id": "fever", "q": "Have you had a fever?"},
    {"id": "allergy", "q" : "Are you allergic to anything?" },
    {"id": "medications", "q": "What medications are you currently taking?"},
    {"id": "conditions", "q": "Any chronic conditions?"},
    {"id": "prior_contact", "q": "Have you contacted us about this before?"}
]

```

### Emergency Keywords

Modify red flag detection in `app.py`:

```python
red_flags = [
  "chest pain",
  "shortness of breath",
  "can't breathe",
  "severe bleeding",
  "unconscious",
  "stroke",
  "heart attack"
  
]
```

---

## 🗃️ Database Schema

### Tables

**users**
- `id`: Integer (primary key)
- `email`: Text (unique)
- `password_hash`: Text
- `role`: Text (beneficiary | nurse)
- `created_at`: DateTime

**sessions**
- `id`: Text (UUID, primary key)
- `user_email`: Text
- `state`: Text (enum)
- `summary`: Text (AI-generated)
- `is_read`: Boolean
- `nurse_joined`: Boolean
- `was_urgent`: Boolean
- `intake_json`: Text (JSON)
- `created_at`: DateTime
- `last_activity`: DateTime

**messages**
- `id`: Integer (primary key)
- `session_id`: Text (foreign key)
- `role`: Text (beneficiary | nurse | assistant)
- `content`: Text
- `timestamp`: Text (ISO format)
- `phase`: Text (intake | chat | system | summary | completion)

---

## 🤖 AI Integration

### Gemini Configuration

SmartIntake uses Google's Gemini models with a tiered fallback system:

1. **Primary**: `gemini-2.5-flash` (newest, fastest)
2. **Fallback**: `gemini-2.0-flash`
3. **Final Fallback**: `gemini-1.5-flash`

### Prompt Engineering

The AI is constrained with strict system instructions:

```python
instructions = """You are a medical intake assistant. 
Your only task is to summarize the patient's answers into a 
short, professional note for a nurse. Describe the symptoms 
and current situation clearly. 

Strictly forbidden: Do not provide medical advice, 
suggestions, diagnoses, or care plans."""
```

### Summary Generation

Located in `logic.py`:

```python
async def generate_intake_summary(s: ChatSession):
    # Compiles all intake Q&A
    # Sends to Gemini with strict instructions
    # Stores result in session.summary
```

---

## 🔐 Security Features

### Authentication

- **Bcrypt** password hashing (12 rounds)
- **Session-based** authentication (cryptographically signed cookies)
- **Role-based** access control (RBAC)
- **Login required** decorator for protected routes

### Authorization

```python
@login_required
def protected_route(request):
    # Only authenticated users
    ...

def require_role(request: Request, role: str):
    # Only users with specific role
    ...
```

### Data Protection

- SQL injection prevention (parameterized queries)
- XSS protection (FastHTML auto-escaping)
- CSRF tokens (Starlette sessions)
- Foreign key constraints
- Input validation


---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/AmazingFeature`
3. **Commit your changes**: `git commit -m 'Add some AmazingFeature'`
4. **Push to the branch**: `git push origin feature/AmazingFeature`
5. **Open a Pull Request**

### Contribution Ideas

- Improve UI/UX design
- Add automated tests
- Implement new features from roadmap
- Fix bugs or improve documentation
- Optimize database queries
- Enhance AI prompts

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/MrCzaro/SmartIntake/issues)
- **Discussions**: [GitHub Discussions](https://github.com/MrCzaro/SmartIntake/discussions)
- **Email**: cezary.tubacki@gmail.com

---

## 🙏 Acknowledgments

- **[FastHTML](https://fastht.ml/)**: Modern Python web framework
- **[MonsterUI](https://monsterui.dev/)**: Beautiful UI component library
- **[Google Gemini](https://ai.google.dev/)**: Advanced AI language model
- **[HTMX](https://htmx.org/)**: Dynamic HTML with minimal JavaScript
- **[DaisyUI](https://daisyui.com/)**: Tailwind CSS component library

---

## ⚖️ Medical Disclaimer

**THIS SOFTWARE IS PROVIDED FOR INFORMATIONAL PURPOSES ONLY.**

SmartIntake is a triage and screening tool that assists healthcare professionals. It is NOT intended to:
- Diagnose medical conditions
- Provide medical advice or treatment
- Replace professional medical judgment
- Be used in emergency situations without professional oversight

**Always seek the advice of your physician or other qualified health provider with any questions you may have regarding a medical condition.**

---

## 📊 Project Stats

- **Language**: Python 3.11+
- **Framework**: FastHTML
- **Lines of Code**: ~2,000+
- **Files**: 7 core modules
- **Database**: SQLite
- **UI Components**: MonsterUI + Custom

---

Made with ❤️ by [MrCzaro](https://github.com/MrCzaro)

**Star ⭐ this repo if you find it useful!**

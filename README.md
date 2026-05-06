# Investment Portfolio Tracker with AI Conversational Financial Assistant Using Retrieval-Augmented Generation (RAG)

## Setup

**Requirements:** Python 3.10+, Node.js 18+, npm

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Environment Variables

Create a `.env` file in the `backend/` directory with the following:

```
GROQ_API_KEY=your_groq_api_key_here
```

`GROQ_API_KEY` — Used for AI response generation via the Groq API.

---

## How to Use

1. Register a new account or log in with existing credentials.
2. Add holdings manually or import existing positions.
3. Execute buy or sell trades through the trade modal.
4. View the portfolio dashboard to see analytics and allocation metrics.
5. Open the AI assistant panel and ask financial questions about your portfolio.
6. Review AI-generated responses and sentiment insights for your holdings.

---

## Project Structure

```
backend/
  core/           # Models, authentication, audit logging
  services/       # AI, forecasting, market intelligence logic
  api/            # REST API views and serializers

frontend/
  src/
    components/   # Reusable UI components
    pages/        # Route-level page components
    context/      # Global auth and state context
```

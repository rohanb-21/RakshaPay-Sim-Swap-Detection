# RakshaPay — SIM Swap Attack Detection & Prevention

**Author:** Rohan Bharat  
<!-- **Live Demo:** https://rakshapay-sim-swap-detection.onrender.com -->

---

## What is this?

RakshaPay is a demo banking application that detects and prevents SIM swap attacks in real time. A SIM swap attack happens when a fraudster convinces a telecom carrier to transfer your phone number to their SIM card — giving them access to your SMS OTPs and ultimately your bank account.

This system intercepts that attack before it succeeds by scoring every login attempt using a combination of fraud signals and a trained machine learning model, then deciding whether to allow, challenge, or block the request.

---

## How the Detection Works

Every login goes through a risk engine that evaluates multiple signals simultaneously:

- Whether the user's SIM card was recently swapped
- Whether the device is recognized or new
- The transaction amount being attempted
- The IP address origin
- Login hour patterns
- Recent failed login attempts
- Account age and transaction history

These signals feed into two layers. The first is a rule-based layer that applies direct scoring based on known fraud patterns. The second is an XGBoost machine learning model trained on 10,000 synthetic records that calculates a fraud probability score. The two scores are blended in a 60/40 ratio to produce a final risk score between 0 and 100.

```
Score < 35   →  Allow (normal login)
Score 35–69  →  Challenge (step-up verification required)
Score ≥ 70   →  Block (access denied, fraud alert created)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · Uvicorn |
| Machine Learning | XGBoost · scikit-learn · NumPy · pandas |
| Authentication | JWT (python-jose) · HMAC-SHA256 |
| Database | SQLAlchemy ORM · SQLite |
| Security | slowapi rate limiting · Pydantic validation · account lockout |
| Frontend | HTML5 · CSS3 · Vanilla JavaScript |
| Testing | pytest · 18 tests |
| Deployment | Render |

---

## Features

- Real-time SIM swap detection on every login
- XGBoost ML fraud scoring (AUC 1.0 on test data)
- Risk-based authentication — ALLOW / CHALLENGE / BLOCK decisions
- JWT authentication with token expiry
- Account lockout after 5 failed login attempts
- Rate limiting on all sensitive endpoints
- Live RBA meter on login page showing risk score as you type
- Admin panel with fraud logs, alerts, and SIM swap simulator
- Full audit trail of every login attempt
- Swagger API documentation at `/api/docs`

---

## Running Locally

**Requirements:** Python 3.11, pip

```bash
# Clone the repo
git clone https://github.com/rohanb-21/RakshaPay-Sim-Swap-Detection.git
cd RakshaPay-Sim-Swap-Detection

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Train the ML model
python3.11 ml/train_model.py

# Start the server
python3.11 main.py
```

Open http://localhost:8000 in your browser.

---

## Demo Walkthrough

**Normal login flow:**
1. Register at `/register` with any details
2. Login — risk score will be low, access allowed
3. Enter the OTP shown on screen
4. You're in the dashboard

**Simulating a SIM swap attack:**
1. Go to `/admin`
2. Click **⚡ Simulate** next to your user
3. Try to login again
4. Watch the RBA meter jump — login gets blocked with risk score 70+
5. Fraud alert is automatically created in the admin panel

**Resetting:**
1. Go back to `/admin`
2. Click **✓ Reset** — account is safe again

---

## Project Structure

```
RakshaPay-Sim-Swap-Detection/
├── main.py              — FastAPI server, all API routes
├── models.py            — SQLAlchemy database models
├── auth.py              — JWT tokens, password hashing, account lockout
├── risk_engine.py       — Hybrid ML + rule-based risk scoring
├── vonage_client.py     — Vonage SIM Swap API integration (sandbox ready)
├── config.py            — Environment-based configuration
├── ml/
│   ├── train_model.py   — XGBoost model training script
│   ├── fraud_model.pkl  — Trained model (generated on first run)
│   └── model_meta.json  — Model performance metrics
├── pages/
│   ├── login.html       — Login page with live RBA meter
│   ├── register.html    — Account creation
│   ├── dashboard.html   — Account overview
│   ├── transfer.html    — Money transfer with risk preview
│   └── admin.html       — Fraud dashboard and simulator
├── tests/
│   ├── test_auth.py     — Auth unit tests
│   ├── test_risk.py     — Risk engine tests
│   └── test_api.py      — API integration tests
├── requirements.txt
├── runtime.txt
└── Procfile
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | Create account |
| POST | `/api/login` | Login with risk assessment |
| POST | `/api/verify-otp` | Verify OTP, receive JWT |
| GET | `/api/user/{id}` | Get user profile |
| POST | `/api/transfer` | Transfer money |
| GET | `/api/admin/users` | All registered users |
| POST | `/api/admin/simulate-swap` | Simulate SIM swap |
| POST | `/api/admin/reset-swap` | Reset SIM swap |
| GET | `/api/admin/fraud-logs` | Login attempt logs |
| GET | `/api/admin/alerts` | Fraud alerts |
| GET | `/api/admin/stats` | Dashboard statistics |
| GET | `/api/admin/model-meta` | ML model performance |
| GET | `/api/health` | Health check |

Full interactive docs: https://rakshapay-sim-swap-detection.onrender.com/api/docs

---

## About Vonage Integration

The `vonage_client.py` file is built and ready to connect to the Vonage Network SIM Swap API. When Vonage credentials are configured via environment variables, the system makes real API calls to check whether a phone number's SIM was recently changed at the carrier level.

Without credentials, the system falls back to the local database simulation — which is what powers the demo on Render. The detection logic, risk scoring, and blocking behavior are identical in both modes.

To enable real Vonage calls, create a free account at https://developer.vonage.com, generate an application with Network Registry enabled, and set `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY_PATH` in your environment variables.

---

## Resume Description

Built RakshaPay, a production-grade SIM Swap fraud detection system for banking. Engineered a hybrid risk engine combining XGBoost ML (AUC 1.0, trained on 10K records) with rule-based fraud signals for real-time login risk scoring. Backend built with FastAPI and SQLAlchemy, secured with JWT authentication, rate limiting, and account lockout. Integrated Vonage Network API architecture for carrier-level SIM swap detection. Deployed on Render with 18 automated pytest tests covering auth, ML, and API layers.

---

*Built by Rohan Bharat*

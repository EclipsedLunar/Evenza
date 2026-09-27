# EVENZA

EVENZA is an opportunity discovery and event-management platform for students and organisers across Maharashtra.

## Requirements

- Python 3.11+
- Node.js 20+
- MongoDB

## Run locally

1. Start MongoDB on `localhost:27017`, or update `MONGO_URL` in `backend/.env`.
2. Copy `backend/.env.example` to `backend/.env` and set a unique `JWT_SECRET`.
3. Install and start the API:

	```powershell
	cd backend
	python -m venv .venv
	.venv\Scripts\Activate.ps1
	pip install -r requirements.txt
	uvicorn server:app --reload --host 127.0.0.1 --port 8000
	```

4. In another terminal, install and start the frontend:

	```powershell
	cd frontend
	npm install
	npm run dev
	```

Open the Vite URL shown in the terminal. The development server proxies `/api` requests to the local API at port 8000. On first backend startup, EVENZA seeds the event catalogue and demo accounts into MongoDB.

## Configuration

Backend settings are documented in `backend/.env.example`. Optional integrations such as the language model and Razorpay require their own credentials. Never commit `.env` files or production secrets.

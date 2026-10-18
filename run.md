cd "d:\Extra Project\EGS_Haspital\backend"

# 1. Create Python Virtual Environment (venv)
python -m venv .venv

# 2. Activate Virtual Environment
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Run the default users seeder
python -m scripts.seed_defaults

# 6. Start the backend API server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000




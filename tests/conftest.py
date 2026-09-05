import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# app/ is not an installed package (it's UI code, kept out of the
# computational_life distribution); make it importable for tests the
# same way `streamlit run app/streamlit_app.py` would.
sys.path.insert(0, str(REPO_ROOT / "app"))

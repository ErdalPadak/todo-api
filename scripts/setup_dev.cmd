python -m pip install -U pip
pip install -r requirements.txt 2>$null
pip install black ruff mypy pytest pre-commit
pre-commit install

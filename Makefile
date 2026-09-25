.PHONY: install test lint notebook-check clean

install:
	python -m pip install -e .
	python -m pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	black --check src/ tests/
	isort --check-only --profile black src/ tests/
	flake8 --max-line-length=110 src/ tests/
	bandit -r src/ -q

notebook-check:
	python scripts/check_notebook_syntax.py

clean:
	find . -type d -name "__pycache__" -not -path "./data/*" -exec rm -rf {} +
	find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} +

PY ?= python

.PHONY: setup ask demo serve eval eval-bedrock checker-eval cost test lint validate-infra

setup:            ## virtualenv with dev dependencies
	$(PY) -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

demo:             ## a few questions in English, Nepali and romanised Nepali (rules backend, no AWS)
	$(PY) -m sodhnus ask "How unusual was the rain in Kathmandu on असोज १२, 2081?"
	$(PY) -m sodhnus ask "२०८१ असोज १२ मा कहाँ सबैभन्दा धेरै पानी पर्यो?"
	$(PY) -m sodhnus ask "Melamchi rainfall on 15 June 2021"
	$(PY) -m sodhnus ask "Dhankuta monsoon total 2014"
	$(PY) -m sodhnus ask "bholi ktm ma pani parchha ki?"

serve:            ## HTTP API on :8000 (try /docs)
	$(PY) -m sodhnus serve

eval:             ## the 60-question evaluation set, rules backend -> eval/results/rules.json
	$(PY) eval/run_eval.py

eval-bedrock:     ## the same set against Amazon Nova Lite (needs AWS credentials and model access)
	$(PY) eval/run_eval.py --backend bedrock

checker-eval:     ## how many wrong answers the checker catches, and how many right ones it rejects
	$(PY) eval/checker_mutations.py

cost:             ## monthly cost model behind docs/COST.md
	$(PY) scripts/cost_model.py

test:
	$(PY) -m pytest -q

lint:
	ruff check .

validate-infra:   ## lint the SAM/CloudFormation template
	cfn-lint infra/template.yaml

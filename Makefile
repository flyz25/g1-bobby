PYTHON ?= .venv/bin/python
UVICORN ?= .venv/bin/uvicorn

.PHONY: dev-api dev-up dev-test dev-doctor unitree-report unitree-sim-trace

dev-api:
	$(UVICORN) g1_bobby_api.app:app --host 127.0.0.1 --port 8010

dev-up:
	./scripts/dev_up.sh

dev-test:
	$(PYTHON) -m pytest

dev-doctor:
	./scripts/dev_doctor.sh

unitree-report:
	./scripts/unitree_report.sh

unitree-sim-trace:
	./scripts/unitree_sim_trace.sh

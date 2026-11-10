.PHONY: test verify smoke tables figures list
verify:
	python reproduce.py verify
test:
	python -m pytest -q tests repro/review6_20261109/test_optimized.py repro/w1w4_20261110/test_baselines.py repro/cert_age_slo_20261110/test_controls.py
smoke:
	python reproduce.py smoke --output runs/smoke
tables:
	python reproduce.py tables --output runs/tables
figures:
	python reproduce.py figures --output runs/figures
list:
	python reproduce.py list

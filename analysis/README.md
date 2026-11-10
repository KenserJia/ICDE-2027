# Current and historical displays

`python reproduce.py tables --output runs/tables` rebuilds and checks the six current body tables from indexed per-entity/per-run values. `python reproduce.py figures --output runs/figures` regenerates the two current figures. Current reconstruction is in `src/mtmemory_artifact/current.py`; the older `analysis.py` and prior figure drivers remain as historical generators and are not the default current-paper entry points.

Current tables: I reach/error; II same-statistic certificate and layout controls; III request-age prior; IV joint recovery; V certificate/fusion cost; VI quality/p99/timely-completion feasibility. Current figures: joint framework and paired load region. `evidence/PAPER_MAP.json` maps these to exact records. Older controlled triptych, symmetric-scope and joint-operating figures remain in `figures/recorded/` solely for historical evidence; they are not current body Figures3/4.

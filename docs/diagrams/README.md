# UML diagrams

Sources are Mermaid (`*.mmd`); `*.svg` and `*.png` (2x) are generated with `.venv/bin/python scripts/render_diagrams.py`
(Playwright, from `requirements-dev.txt`). Edit the `.mmd` file, then re-render. All diagrams were checked against the
code on 4 Oct 2026 (statuses from the model constraints, routes from the API controllers, arrows from the imports).

| File | Diagram | Shows |
|---|---|---|
| `01_use_case` | Use case | The three roles and the CLI operator, with their use cases inside the system boundary (Mermaid has no use-case notation, so actors are boxes labelled «actor»). |
| `02_class_menu_inventory` | Class | Menu items and recipes, ingredients, suppliers, stock batches and movements, purchase orders, kitchen stock requests. |
| `03_class_forecasting_kitchen` | Class | Sales and context data, model versions, forecast runs and forecasts, recommendations, pre-orders, orders, preparation, waste, alerts. |
| `04_class_services` | Class (layers) | The service layer and the `ml` package with their main operations; arrows are the imports as built. |
| `05_seq_forecast_run` | Sequence | Generating the 7-day forecast, including the skipped and failed paths. |
| `06_seq_prep_decision` | Sequence | Kitchen opens the prep plan and accepts or overrides a recommendation. |
| `07_seq_po_receipt_alert` | Sequence | Receiving a purchase order, and the stock-out alert closing on the next alert evaluation. |
| `08_act_daily_cycle` | Activity | The daily forecast-to-purchase cycle across the system and both manager roles. |
| `09_act_stock_request` | Activity | A kitchen stock request from creation to issue or rejection, with the all-or-nothing stock check. |

The ER diagram is in `docs/DATABASE.md`; the layer and service-graph diagrams of the original design are in
`docs/ARCHITECTURE.md` (the as-built service graph is `04_class_services`).

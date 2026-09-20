# Application Source

Project-owned Python packages for ingestion, reconciliation, orchestration, and realtime serving.

Realtime components:

- `realtime/consumer.py` - Service Broker consumer and PostgreSQL current-state projection worker
- `realtime/api.py` - PostgreSQL-backed REST and Server-Sent Events serving service

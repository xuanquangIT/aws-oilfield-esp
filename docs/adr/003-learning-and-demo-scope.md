# ADR 003: One customer story, separate exam extensions

Status: accepted, 2026-09-05.

Context: DEA-C01 covers more service choices than a small ESP pipeline should deploy permanently.

Decision: demonstrate ingestion, transformation, state/history storage, quality, recovery, security and cost through one product. Map remaining task subskills to explicit study or temporary extension labs. Phase 1 requires a local-first browser dashboard with no additional deployed AWS service or paid BI subscription. A separately deployed static/serverless hosted profile is optional for an external customer URL.

Consequences: the project can address all task groups without claiming every skill is hands-on. Exam readiness remains a learner assessment. The local dashboard runs only during demos and can still add small DynamoDB/S3 request usage. Temporary labs and the optional hosted dashboard must have independent cleanup and must not change the parked baseline without a reviewed cost decision.

# Documentation hub

The project documentation has nine primary documents. Each has one owner and one purpose; detailed decisions remain in ADRs.

| Document                                                         | Use it for                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [Getting started](01-GETTING-STARTED.md)                         | Local setup, AWS authentication, bootstrap, first deploy and reset                    |
| [Architecture](02-ARCHITECTURE.md)                               | Current dataflow, target pipeline, stack boundaries and trade-offs                    |
| [Data domain and contract](03-DATA-DOMAIN-AND-CONTRACT.md)       | ESP meaning, representative sources, units, schemas, validation and lineage           |
| [Operations](04-OPERATIONS.md)                                   | Batch/realtime runs, observation, parking, recovery, timing and troubleshooting       |
| [Cost, security and governance](05-COST-AND-SECURITY.md)         | Monthly scenarios, cost controls, IAM boundaries, audit and data governance           |
| [Delivery, acceptance and learning](06-DELIVERY-AND-LEARNING.md) | M0-M6 implementation, evidence gates, DEA-C01 coverage and guided labs                |
| [Demo and dashboard](07-DEMO-AND-DASHBOARD.md)                   | Local dashboard contract, optional hosted profile and customer rehearsal              |
| [Sources](08-SOURCES.md)                                         | Official AWS and equipment references                                                 |
| [Runbook](09-RUNBOOK.md)                                         | Single linear command reference: deploy, run every scenario, verify, park and destroy |

Recommended routes:

- Builder: Getting started -> Architecture -> Data -> Delivery -> Operations.
- Operator: Getting started -> Operations -> Cost and security.
- Customer or interviewer: Architecture -> Demo and dashboard -> Acceptance section in Delivery.
- DEA-C01 learner: Architecture -> Delivery and learning -> Operations -> Cost and security.

Phase 1 scope is a complete flow from batch/realtime ingestion through validated publication, Athena query and local consumer dashboard. Start with [project status](../PROJECT-STATUS.md) for the implemented/planned boundary; it is incomplete until M1-M5 pass their evidence gates.

Documents are written in English for customer and contributor reuse. Commands target Windows PowerShell.

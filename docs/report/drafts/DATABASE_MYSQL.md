# Draft report text: the database (MySQL 8.4)

*Drafted 9 October 2026 on branch `feature/mysql` for the technology section (report 6.2) and the deployment section
(report 9.3). It replaces the earlier draft that justified MariaDB. **Use the cutover sentence only if the production
cutover has actually been carried out**; otherwise use the alternative sentence. Figures marked [CONFIRM] are filled in
from `docs/TEST_LOG.md` section 17.*

---

**Database management system.** As planned in the proposal (section 8.3), SmartRestaurant stores its data in
**MySQL**: MySQL Community Server 8.4 LTS, run as a private database instance for the project, reachable only from the
server itself. The schema (30 tables, 67 foreign keys, 44 CHECK constraints and 15 unique keys) is created by the
project's Alembic migrations, and the application uses only database-independent SQLAlchemy types.

*Cutover sentence:* During development the demonstration ran on a private MariaDB 11.8 instance (a MySQL-compatible
fork). On [CONFIRM: date] the data was moved to MySQL: a verified copy of all 24,440 rows was loaded through the
migrations, and every table's row count and content checksum, and all 67 foreign keys, were checked to be identical
before the application was switched over.

*Alternative sentence (no cutover):* The demonstration server still runs on a private MariaDB 11.8 instance (a
MySQL-compatible fork); the MySQL 8.4 instance was built and tested in parallel, with a verified copy of all data, and
the switch-over is documented but was not carried out before the demonstration.

**Testing on MySQL.** The full automated test suite was run against MySQL 8.4 [CONFIRM: n passed, 0 failed],
including the constraint and concurrency tests (two simultaneous stock-outs never make stock negative), and the
complete demonstration pipeline (seeding, synthetic history, training, backfill, forecasting and alerts) ran on MySQL.

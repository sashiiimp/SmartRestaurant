# Draft report text: MariaDB instead of MySQL (justified deviation)

*Drafted 9 October 2026 for the technology section (report 6.2) and the deviations or limitations section. Not yet in
`REPORT.md`; the team decides where it goes.*

---

**Database management system.** The proposal named MySQL as the DBMS (proposal section 8.3). The implemented system
uses **MariaDB 11.8**, run as a private database instance for this project. MariaDB is a fork of MySQL that keeps the
MySQL client protocol and SQL dialect, so the application connects to it through the same MySQL driver (PyMySQL) and
uses the same storage engine (InnoDB), data types, constraints and transactions that the design relied on. MariaDB was
chosen because it is the database server already installed on the project's hosting machine; running a separate
private instance of it kept the project's data apart from the other websites on that server without installing and
maintaining a second database product. **[TEAM: confirm this reason; the project records only that the server runs MariaDB 11.8 as a private instance.]** The application code uses only database-independent SQLAlchemy types and
Alembic migrations, and its automated tests run on SQLite and on MariaDB.

The change does not affect any functional requirement: every table, relationship and constraint planned for MySQL
exists in MariaDB. Two differences were found and handled during testing: MariaDB reports a violated CHECK constraint
as error 4025, and under concurrent stock-outs a locking read can fail with error 1020; the stock services retry such
operations, and a concurrency test confirms that stock never becomes negative. The services also handle MySQL's own
lock errors (1213 and 1205). **The system has not been tested on MySQL itself**, so "MySQL-compatible" is a design
property, not a tested claim; running the test suite against MySQL 8.4 would confirm it.

*Suggested limitation (one line):* "The system runs on MariaDB 11.8, a MySQL-compatible fork, instead of the proposed
MySQL; compatibility with MySQL itself has not been tested."

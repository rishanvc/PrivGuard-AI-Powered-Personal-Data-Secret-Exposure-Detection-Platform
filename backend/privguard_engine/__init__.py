"""PrivGuard detection engine.

This package is deliberately framework-free: it MUST NOT import Django
or anything under apps/ or config/. Django calls into this package; this
package never calls back. That boundary is what lets detection rules be
unit-tested without a database or a running web application (SRS NFR-039).
"""

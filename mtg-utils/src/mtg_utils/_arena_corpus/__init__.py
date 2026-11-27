"""Sanitized Arena logs for a public log corpus (ADR-0067; ``arena-log-export``).

``scrub`` installs and runs the Manasight scrubber, ``redact`` is the second pass
for what it misses, ``verify`` the fail-closed checks, ``naming`` the corpus file
names, ``corpus`` the manifest, state file and commit, ``export`` the pipeline.
"""

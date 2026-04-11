"""Source adapters for hot-events-radar.

Each source returns a list[CandidateEvent]. Graceful failure: returns []
on network error, never raises. Sources must be individually testable
against static fixtures.
"""

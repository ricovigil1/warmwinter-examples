"""Unreleased source SDK required; owner-authorized advisory persistence only.

This grant is separate from a Gate/run key and grants no execution authority.
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ["WARMWINTER_CONSULTATION_KEY"])
catalog = ww.consultation_capabilities()
print("Admitted capabilities:", [entry["name"] for entry in catalog["capabilities"]])
reading = ww.consult_queue(arrival_rate=8, service_capacity=10,
                          rate_unit="tasks/minute", source_ref="example:synthetic-rates",
                          usefulness_confidence=0.6)
retained = ww.consultation(reading["consultation_id"])
print("Advisory regime:", retained["analysis"]["regime"])

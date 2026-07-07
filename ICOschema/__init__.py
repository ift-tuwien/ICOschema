"""ICOschema: a backend-agnostic data model for sensor/hardware measurements.

    from ICOschema import Measurement

    measurement = Measurement.from_hdf5("some_file.hdf5")
    df = measurement.to_dataframe()

See ICOschema.model.python.measurement.Measurement for the full API.
"""

from ICOschema.model.python.measurement import Measurement

__all__ = ["Measurement"]

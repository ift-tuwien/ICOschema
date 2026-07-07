# ICOschema

Other codebases should only import `Measurement` from the top-level package:

```python
from ICOschema import Measurement

measurement = Measurement.from_hdf5("some_file.hdf5")
df = measurement.to_dataframe()
plt.plot(measurement.timestamps, measurement.channel1)
```

Regenerate the Python dataclasses after editing the schema:

``uv run gen-python .\ICOschema\schema\linkml\measurement.yaml > .\ICOschema\schema\generated\python\measurement.py``

Run the tests:

``uv run pytest``
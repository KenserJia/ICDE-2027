# Data attribution and transformations

The raw and processed observations are reused public datasets under **CC BY 4.0**. Their license is independent of the MIT software license. The full license is in `licenses/CC-BY-4.0.txt` and at https://creativecommons.org/licenses/by/4.0/ . Include the original dataset citations and describe preprocessing when redistributing the arrays.

- Hadi Fanaee-T (2013), **Bike Sharing**, UCI Machine Learning Repository, DOI: https://doi.org/10.24432/C5W894 . Source: https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset . Uses `hour.csv`:17,379 observations, channels `cnt,temp,hum,windspeed`. This is an aggregate hourly series, not individual riders.
- Song Chen (2017), **Beijing Multi-Site Air Quality**, UCI Machine Learning Repository, DOI: https://doi.org/10.24432/C5RK5G . Source: https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data . Twelve station files in sorted filename order,35,064 observations each, channels `PM2.5,TEMP,PRES,WSPM`. Raw source attribution to the Beijing monitoring center and China Meteorological Administration is retained through the UCI source record.

Changes: select four variables; preserve file/ingestion order; causally forward-fill nonfinite values using zeros before the first valid observation; chronological60/20/20split; compute mean/std on training data only, floor std at1e-6; standardize to float32. Mean/std arrays remain float64. No future values are used to fill gaps. Civil-hour gaps are not inserted; query distances are observation steps. Processed channels are dimensionless standardized values. Raw variable units and original weather scaling are given by UCI.

Bike split counts:10,427/3,476/3,476. Each station:21,038/7,013/7,013. NPZ keys are `train_i`, `validation_i`, `test_i` (rows×4,float32), and `mean_i`,`std_i` (4,float64). `SOURCES.json` preserves exact upstream archive URLs and SHA-256; per-dataset JSON files give entity/split counts.

```sh
python reproduce.py prepare-data --output runs/rebuilt-data
```

This rebuilds the arrays from bundled raw ZIPs and requires exact numerical equality with every published NPZ array, including means/stds. The regenerated ZIP container bytes may differ while array values remain identical. `PREPARATION.json` records station filenames and missing-value counts. Neither source is represented as a production query or change-data-capture log; request schedules are controlled experimental code.

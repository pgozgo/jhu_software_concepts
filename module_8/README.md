# Module 8: Grad Café Data Analysis

Run `module_8.ipynb` top to bottom in SageMaker. It loads the Grad Café JSON from S3 with boto3, cleans it, runs the SciPy analysis, saves the plots, and writes `analytics.pdf`. It then exports `cleaned_gradcafe.json` and uploads it back to S3.

## Deliverables

- `module_8.ipynb`, `analytics.pdf`, `cleaned_gradcafe.json`
- `missingness_summary.csv`, `summary_statistics.csv`
- Screenshots: `initial_dataframe.png`, `missingness_summary.png`, `low_program_count.png`, `date_based.png`, `float_columns.png`, `outlier_summary.png`
- Plots: `GRE-vs-GRE-V.png`, `GPA-vs-GRE.png`, `Degree-vs-International.png`, `Acceptances-over-Time.png`, `GPA-by-Outcome.png`, `Numeric-Correlation-Heatmap.png`

## Notes

- `application_season`: June-July = Early Cycle, August-September = Mid Cycle, October-December = Late Cycle; other months or missing dates = Unknown.
- `days_to_decision` = `decision_date - date_added`. It is often negative because entries are posted after the decision; `decision_speed` marks those as `Unknown`.

## Quick API examples

Minimal examples of the main libraries used in the notebook.

### pandas

```python
import pandas as pd

df = pd.DataFrame({"degree": ["PhD", "Master's", "PhD"], "gpa": [3.9, 3.5, None]})
df.head(5)                                   # first rows
df.shape, df.dtypes                          # rows/columns, column types
df.isnull().sum()                            # missing count per column
df["gpa"].mean()                             # skips NaN by default
df[df["degree"] == "PhD"]                    # filter rows
df["degree"].value_counts()                  # occurrences of each value
pd.to_datetime("Added on Sep 20, 2026".replace("Added on ", ""))  # text -> datetime
pd.crosstab(df["degree"], df["gpa"] > 3.6)   # contingency table
df.to_json("out.json", orient="records")     # export
```

### NumPy

```python
import numpy as np

x = np.array([1, 2, 3, 4]); y = np.array([2, 4, 6, 9])
np.mean(x), np.std(x, ddof=1)                # statistics
slope, intercept = np.polyfit(x, y, 1)       # best-fit line y = slope*x + intercept
days = np.array([5, 45, 90, np.nan])
np.select([days <= 30, days <= 60, days > 60],
          ["0-30 days", "31-60 days", "61+ days"], default="Unknown")
```

### SciPy

```python
from scipy.stats import zscore, pearsonr, ttest_ind, chi2_contingency

zscore([1, 2, 3, 100])                       # standardize; |z| > 3 = outlier
r, p = pearsonr(x, y)                        # correlation coefficient and p-value
t, p = ttest_ind([3.8, 3.9], [3.5, 3.6], equal_var=False)  # two-sample t-test
chi2, p, dof, expected = chi2_contingency([[10, 20], [30, 40]])
```

### Matplotlib

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(8, 5))
ax.scatter(x, y, label="Data")               # scatter plot
ax.plot(x, slope * x + intercept, label="Best fit")
ax.set_title("Example"); ax.set_xlabel("X (units)"); ax.set_ylabel("Y (units)")
ax.legend()
fig.savefig("example.png", dpi=200, bbox_inches="tight")  # one PNG per figure
# other chart types: ax.bar(...), ax.hist(data, bins=...), ax.boxplot([a, b])
```

### boto3

```python
import boto3

s3 = boto3.client("s3")
s3.download_file("bucket", "applicant_data.json", "local.json")
s3.upload_file("cleaned_gradcafe.json", "bucket", "cleaned_gradcafe.json")
```

## Shutdown reminder

After the notebook finished, the SageMaker notebook instance was **stopped** to avoid further charges.

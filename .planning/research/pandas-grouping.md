# Pandas 2-Quarter Grouping Research

## Approach

### Option A: `pd.Grouper` with `freq='2Q'`
```python
df['transition_date'] = pd.to_datetime(df['transition_date'])
grouped = df.groupby(pd.Grouper(key='transition_date', freq='2Q'))
```
- Aligns to calendar quarter boundaries: Q1 (Jan-Mar), Q2 (Apr-Jun), Q3 (Jul-Sep), Q4 (Oct-Dec)
- 2Q means Q1-Q2, Q3-Q4 groupings
- Period labels follow pandas quarter conventions

### Option B: `freq='6ME'`
```python
grouped = df.groupby(pd.Grouper(key='transition_date', freq='6ME'))
```
- 6-month end frequency
- More flexible start boundaries
- Less intuitive period labels

**Recommendation**: Use `freq='2Q'` for clear calendar-aligned periods.

## Output Format
```python
result = []
for period, group in grouped:
    attempts = (group['action_type'] == 'ATTEMPT').sum()
    returns = (group['action_type'] == 'RETURN').sum()
    result.append({
        'period': f"{period.year} Q{period.quarter}-Q{period.quarter+1}",
        'attempts': int(attempts),
        'returns': int(returns),
        'return_rate_pct': round((returns / attempts * 100) if attempts else 0, 1)
    })
```

## Alternative: Manual label formatting
Pandas `Grouper` with `freq='2Q'` produces `Period` objects. To get labels like "2024 Q1-Q2", extract year and compute quarter ranges manually from the period start and end.

## Edge Cases
- Empty dataset → return empty list `[]`
- All attempts, zero returns → `return_rate_pct: 0.0`
- Zero attempts in a period → skip or show 0
- Partial current period → include all available data (sync handles date filtering)

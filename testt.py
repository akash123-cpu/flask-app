import pandas as pd

df = pd.read_csv('1C9DC2D6B329_enriched.csv', low_memory=False)
df['date_time'] = pd.to_datetime(df['date_time'], format="%d/%m/%y %H:%M", errors='coerce')
print(df.head())
print(df['date_time'].min(), df['date_time'].max())

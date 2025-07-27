from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CSV to Parquet").getOrCreate()

df = spark.read.csv("/opt/airflow/data/input.csv", header=True, inferSchema=True)

# Minimal transformation
df_cleaned = df.dropna()

df_cleaned.write.mode("overwrite").parquet("/opt/airflow/data/output/")
spark.stop()

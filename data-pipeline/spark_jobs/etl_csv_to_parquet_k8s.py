from pyspark.sql import SparkSession


def main():
    spark = SparkSession.builder.appName("ETL CSV to Parquet").getOrCreate()

    # Replace with your S3 bucket paths
    input_path = "s3a://your-bucket/raw-data/input.csv"
    output_path = "s3a://your-bucket/parquet-data/output"

    df = spark.read.option("header", "true").csv(input_path)
    df = df.dropna()
    df.write.mode("overwrite").parquet(output_path)

    spark.stop()


if __name__ == "__main__":
    main()

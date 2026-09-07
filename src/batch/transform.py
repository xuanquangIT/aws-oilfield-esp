import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql import types as T

args = getResolvedOptions(sys.argv, ["JOB_NAME", "DATA_BUCKET"])
sc = SparkContext()
gc = GlueContext(sc)
spark = gc.spark_session
job = Job(gc)
job.init(args["JOB_NAME"], args)

schema = T.StructType(
    [
        T.StructField("schema_version", T.IntegerType()),
        T.StructField("event_id", T.StringType()),
        T.StructField("timestamp", T.StringType()),
        T.StructField("esp_id", T.StringType()),
        T.StructField("source", T.StringType()),
        T.StructField("run_id", T.StringType()),
        T.StructField("flow_rate", T.DoubleType()),
        T.StructField("water_cut", T.DoubleType()),
        T.StructField("intake_pressure", T.DoubleType()),
        T.StructField("discharge_pressure", T.DoubleType()),
        T.StructField("motor_temperature", T.DoubleType()),
        T.StructField("motor_current", T.DoubleType()),
        T.StructField("vibration", T.DoubleType()),
        T.StructField("status", T.StringType()),
    ]
)

df = (
    spark.read.option("header", True)
    .schema(schema)
    .csv(f"s3://{args['DATA_BUCKET']}/raw/batch/historical.csv")
)

out = (
    df.withColumn("event_ts", F.to_timestamp("timestamp"))
    .withColumn("event_date", F.to_date("event_ts"))
    .withColumn("oil_rate", F.col("flow_rate") * (F.lit(1.0) - F.col("water_cut")))
)

out.write.mode("overwrite").partitionBy("event_date").parquet(
    f"s3://{args['DATA_BUCKET']}/curated/telemetry/"
)
job.commit()

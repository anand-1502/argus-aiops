"""Published HDFS baselines, for context only.

Source: Le & Zhang, "Log-based Anomaly Detection with Deep Learning: How Far Are We?" (ICSE 2022),
Table 4, HDFS with session grouping and a random 80/20 split of 575,061 sequences
(https://arxiv.org/abs/2202.04301). Numbers are as printed in the paper.

Caveats: results differ widely between papers because splits and protocols differ, and
only the supervised rows are comparable to a supervised XGBoost classifier. LogAnomaly is
left out because its printed precision/recall do not match its printed F1.
"""

BASELINES = {
    "LogRobust (supervised)": {"precision": 0.961, "recall": 1.0, "f1": 0.980},
    "CNN (supervised)": {"precision": 0.966, "recall": 1.0, "f1": 0.982},
    "PLELog (semi-supervised)": {"precision": 0.893, "recall": 0.979, "f1": 0.934},
    "DeepLog (semi-supervised)": {"precision": 0.835, "recall": 0.994, "f1": 0.908},
}

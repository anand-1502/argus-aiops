"""Argus DAGs. Airflow orchestrates; the Argus API runs the work on the host and Airflow polls until it finishes.

  argus_retrain       nightly 02:00   retrain, promote through the gate, run drift checks
  argus_nightly_eval  nightly 03:00   run the agent over the golden incidents, judge groundedness, record the run
"""
import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor

API = os.environ.get("ARGUS_API", "http://host.docker.internal:8000")


def _trigger(job: str, ti):
    r = requests.post(f"{API}/jobs/{job}", timeout=30)
    r.raise_for_status()
    ti.xcom_push(key="job_id", value=r.json()["id"])


def _finished(job_id_task: str, ti) -> bool:
    job_id = ti.xcom_pull(task_ids=job_id_task, key="job_id")
    j = requests.get(f"{API}/jobs/{job_id}", timeout=30).json()
    if j["status"] == "failed":
        raise RuntimeError(f"job failed with exit code {j['returncode']}:\n{j['log']}")
    return j["status"] == "succeeded"


def make_dag(dag_id: str, job: str, cron: str, timeout_hours: int) -> DAG:
    with DAG(dag_id, start_date=datetime(2026, 10, 1), schedule=cron, catchup=False,
             default_args={"retries": 1, "retry_delay": timedelta(minutes=10)}, tags=["argus"]) as dag:
        trigger = PythonOperator(task_id="trigger", python_callable=_trigger, op_kwargs={"job": job})
        wait = PythonSensor(task_id="wait_for_finish", python_callable=_finished, op_kwargs={"job_id_task": "trigger"},
                            poke_interval=60, timeout=timeout_hours * 3600, mode="reschedule")
        trigger >> wait
    return dag


retrain = make_dag("argus_retrain", "retrain", "0 2 * * *", 3)
nightly_eval = make_dag("argus_nightly_eval", "eval", "0 3 * * *", 6)

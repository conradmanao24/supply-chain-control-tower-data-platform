# syntax=docker/dockerfile:1.7
ARG AIRFLOW_VERSION=3.3.1
ARG PYTHON_VERSION=3.12
FROM apache/airflow:slim-${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

COPY requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      -r /tmp/requirements-airflow.txt \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
    && pip check

ENV DBT_VENV=/home/airflow/.dbt-venv
ENV DBT_BIN=/home/airflow/.dbt-venv/bin/dbt
COPY requirements-dbt.txt /tmp/requirements-dbt.txt
RUN --mount=type=cache,target=/tmp/pip-cache \
    python -m venv "${DBT_VENV}" \
    && PIP_CACHE_DIR=/tmp/pip-cache "${DBT_VENV}/bin/pip" install --timeout 120 --retries 10 -r /tmp/requirements-dbt.txt \
    && "${DBT_VENV}/bin/pip" check

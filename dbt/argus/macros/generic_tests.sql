{% test dbt_utils_free_positive(model, column_name) %}
-- a tiny stand-in for dbt_utils' positive check, so the project has no external package to install
select * from {{ model }} where {{ column_name }} is null or {{ column_name }} <= 0
{% endtest %}

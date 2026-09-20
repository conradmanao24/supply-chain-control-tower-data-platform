{% macro surrogate_key(fields) -%}
md5(concat_ws('||'
    {%- for field in fields %}
    , coalesce(cast({{ field }} as text), '<NULL>')
    {%- endfor %}
))
{%- endmacro %}